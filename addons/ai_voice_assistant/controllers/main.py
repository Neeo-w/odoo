import json
import urllib.request
import urllib.error

from odoo import http
from odoo.http import request

# Field types excluded from the schema sent to the AI server
_EXCLUDED_FIELD_TYPES = frozenset({
    'binary', 'html', 'one2many', 'reference', 'serialized',
})
# Maximum number of fields to send in the schema
_MAX_FIELDS = 60


class AIVoiceController(http.Controller):

    @http.route('/ai_voice/process', type='json', auth='user', methods=['POST'])
    def process_voice(self, audio_base64, res_model, res_id=None):
        ICP = request.env['ir.config_parameter'].sudo()
        server_url = ICP.get_param(
            'ai_voice.server_url',
            'http://localhost:8000/v1/process-voice',
        )
        db_uuid = ICP.get_param(
            'ai_voice.db_uuid',
            ICP.get_param('database.uuid', 'unknown'),
        )

        model_schema = self._get_model_schema(res_model)

        payload = {
            'db_uuid': db_uuid,
            'res_model': res_model or '',
            'res_id': res_id,
            'model_schema': model_schema,
            'audio_base64': audio_base64,
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                server_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            return {'success': True, 'data': result}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            return {'success': False, 'error': f'HTTP {e.code}: {error_body}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/ai_voice/resolve_names', type='json', auth='user', methods=['POST'])
    def resolve_names(self, res_model, field_values):
        """Resolve human-readable names to database IDs for many2one fields."""
        if not res_model or res_model not in request.env:
            return {}

        Model = request.env[res_model]
        fields_info = Model.fields_get(attributes=['type', 'relation'])
        resolved = {}

        for field_name, value in field_values.items():
            if field_name not in fields_info:
                resolved[field_name] = value
                continue

            field_type = fields_info[field_name]['type']

            if field_type == 'many2one' and isinstance(value, str):
                relation = fields_info[field_name].get('relation')
                if relation and relation in request.env:
                    records = request.env[relation].name_search(value, limit=1)
                    resolved[field_name] = records[0][0] if records else False
                else:
                    resolved[field_name] = value
            else:
                resolved[field_name] = value

        return resolved

    def _get_model_schema(self, res_model):
        if not res_model or res_model not in request.env:
            return {}
        try:
            all_fields = request.env[res_model].fields_get(
                attributes=['type', 'string', 'required', 'selection'],
            )
            schema = {}
            count = 0
            for fname, finfo in all_fields.items():
                if count >= _MAX_FIELDS:
                    break
                if fname.startswith('_'):
                    continue
                if finfo['type'] in _EXCLUDED_FIELD_TYPES:
                    continue
                entry = {'type': finfo['type'], 'string': finfo.get('string', fname)}
                if finfo['type'] == 'selection' and finfo.get('selection'):
                    entry['selection'] = finfo['selection']
                schema[fname] = entry
                count += 1
            return schema
        except Exception:
            return {}
