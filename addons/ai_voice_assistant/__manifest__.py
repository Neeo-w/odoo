{
    'name': 'AI Voice Assistant',
    'version': '19.0.1.0.0',
    'summary': 'نظام المساعد الصوتي الذكي لأودو',
    'description': """
        يتيح هذا الموديول للمستخدمين التحكم في أودو عبر الصوت.
        يرسل الصوت إلى سيرفر ذكاء اصطناعي خارجي يقوم بتحليله
        وإعادة أوامر منظمة (إنشاء، تعديل، تقرير) تنفذها أودو تلقائياً.
    """,
    'author': 'Odoo AI Voice',
    'category': 'Tools',
    'depends': ['base', 'web', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_voice_assistant/static/src/scss/voice_button.scss',
            'ai_voice_assistant/static/src/js/voice_button.js',
            'ai_voice_assistant/static/src/xml/voice_button.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
