{
    'name': 'CRM Touch',
    'version': '18.0.1.12.0',
    'category': 'CRM',
    'summary': 'Auto-move leads to Design Phase on attachment upload',
    'description': """
        Automatically transitions a Lead/Opportunity to the Design Phase stage
        when an attachment is uploaded while the lead is in the Request for Inspection stage.

        Features:
        - Adds an "Is Design Phase" flag to CRM stages.
        - Overrides ir.attachment.create to detect uploads on CRM leads.
        - Skips the transition if no Design Phase stage is configured (no auto-creation).
        - Posts a chatter note on every automatic stage transition.
    """,
    'author': 'Msoulatioons',
    'depends': ['crm', 'mail', 'bus', 'sale'],
    'data': [
        'security/crm_security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/crm_meeting_wizard_view.xml',
        'views/crm_place_inspection_wizard_view.xml',
        'views/crm_stage_views.xml',
        'data/mail_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
