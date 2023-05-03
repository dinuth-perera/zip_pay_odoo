# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class ZippayController(http.Controller):
    _return_url = '/payment/zippay/return'
    _webhook_url = '/payment/zippay/webhook'

    @http.route(
        _return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False,
        save_session=False
    )
    def zip_return_from_checkout(self, **data):
        """ Process the notification data sent by Zip Pay after redirection from checkout.
            embedded in the return URL
        """
        _logger.info("handling redirection from ZipPay with data:\n%s", pprint.pformat(data))
        request.env['payment.transaction'].sudo()._handle_notification_data('zippay', data)
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def zippay_webhook(self, **data):
        """ Process the notification data sent by Zip Pay to the webhook.
        """
        _logger.info("notification received from Zip Pay with data:\n%s", pprint.pformat(data))
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('zippay', data)
        except ValidationError:  # Acknowledge the notification to avoid getting spammed
            _logger.exception("unable to handle the notification data; skipping to acknowledge")
        return ''  # Acknowledge the notification
