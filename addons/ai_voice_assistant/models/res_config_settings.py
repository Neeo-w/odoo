from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_voice_server_url = fields.Char(
        string='رابط سيرفر الذكاء الاصطناعي',
        config_parameter='ai_voice.server_url',
        default='http://localhost:8000/v1/process-voice',
        help='رابط API سيرفر FastAPI الخاص بمعالجة الصوت',
    )
    ai_voice_db_uuid = fields.Char(
        string='معرّف قاعدة البيانات (UUID)',
        config_parameter='ai_voice.db_uuid',
        help='المعرف الفريد لقاعدة البيانات المسجل في سيرفر الاشتراكات',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res['ai_voice_db_uuid'] = ICP.get_param(
            'ai_voice.db_uuid',
            ICP.get_param('database.uuid', ''),
        )
        return res
