
{
    'name': 'Payment Provider: Zip Pay',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 10,
    'author': 'Dinuth Perera, Core48',
    'website': 'https://dinuth.me',
    'depends': ['payment'],
    'data': [
        'views/payment_zippay_templates.xml',
        'views/payment_provider_views.xml',

        'data/payment_provider_data.xml',
    ],
    'application': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    # cloc settings
    'cloc_exclude': ["**/*.xml",
                     "models/**/*",
                     "data/**/*",
                     "static/**/*",
                     "view/**/*",
                     "__pycache__/**/*",
                     ],
}
