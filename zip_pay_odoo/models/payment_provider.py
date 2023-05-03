import logging
import requests
from werkzeug import urls

from odoo import _, api, fields, models, service
from odoo.exceptions import ValidationError

from odoo.addons.zip_pay_odoo.const import SUPPORTED_CURRENCIES

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(selection_add=[("zippay", "Zip Pay")], ondelete={"zippay": "set default"})
    zippay_api_key = fields.Char(string="Zip Pay API Key", required_if_provider="zippzy", groups="base.group_system")
    zippay_public_key = fields.Char(string="Public Key", required_if_provider="zippay", groups="base.group_system")
    capture_flow = fields.Selection(
        string="Capture Flow",
        selection=[
            ("immediate", "Immediate"),
            ("auth_capture", "Auth & Capture"),
            ("tokenised", "Tokenised"),
        ],
        default="immediate",
        readonly=True,
        required_if_provider="zippay",
        groups="base.group_system",
    )

    def _get_zippay_urls(self):
        self.ensure_one()
        if self.state == "enabled":
            return "#"
        else:
            return "https://global-api.sand.au.edge.zip.co"

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, **kwargs):
        """Override of payment to unlist Zip Pay providers for unsupported currencies."""
        providers = super()._get_compatible_providers(*args, currency_id=currency_id, **kwargs)

        currency = self.env["res.currency"].browse(currency_id).exists()
        if currency and currency.name not in SUPPORTED_CURRENCIES:
            providers = providers.filtered(lambda p: p.code != "zippay")

        return providers

    def _zippay_make_request(self, endpoint, data=None, method="POST"):
        """
        :param str endpoint: The endpoint to be reached by the request
        :param dict data: The payload of the request
        :param str method: The HTTP method of the request
        :return The JSON-formatted content of the response
        :rtype: dict
        :raise: ValidationError if an HTTP error occurs
        """

        self.ensure_one()
        endpoint = f'/merchant/{endpoint.strip("/")}'
        url = urls.url_join(self._get_zippay_urls(), endpoint)
        headers = {
            "accept": "application/json",
            "Zip-Version": "2021-08-25",
            "content-type": "application/json",
            "Authorization": f"Bearer {self.zippay_api_key}",
        }

        try:
            response = requests.request(method, url, json=data, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            _logger.exception("unable to communicate with Zip Pay: %s", url)
            raise ValidationError("Zip Pay: " + _("Could not establish the connection to the API."))
        return response.json()
