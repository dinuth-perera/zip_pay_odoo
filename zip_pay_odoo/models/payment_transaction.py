# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from werkzeug import urls

from odoo import _, models, fields
from odoo.exceptions import ValidationError

from odoo.addons.zip_pay_odoo.controllers.main import ZippayController
from odoo.addons.payment_adyen import utils as zippay_utils


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_specific_rendering_values(self, processing_values):
        """Override of payment to return rendering values."""
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "zippay":
            return res

        payload = self._prepare_zippay_payment_request_payload()
        _logger.info("sending '/checkouts' request for url creation:\n%s", pprint.pformat(payload))
        payment_data = self.provider_id._zippay_make_request("/checkouts", data=payload)

        # The provider reference is set now to allow fetching the payment status after redirection

        checkout_url = payment_data["uri"]
        parsed_url = urls.url_parse(checkout_url)
        url_params = urls.url_decode(parsed_url.query)
        return {"api_url": checkout_url, "url_params": url_params}

    def _retrieve_zippay_checkout(self, checkout_id):
        provider_id = self.env["payment.provider"].search([("code", "=", "zippay")])
        checkout_data = provider_id[0]._zippay_make_request(f"/checkouts/{checkout_id}", method="GET")
        return checkout_data

    def _prepare_zippay_payment_request_payload(self):
        """Create the payload for the payment request based on the transaction values.

        :return: The request payload
        :rtype: dict
        """
        base_url = self.provider_id.get_base_url()
        redirect_url = urls.url_join(base_url, ZippayController._return_url)
        shopper_name = zippay_utils.format_partner_name(self.partner_name)

        payload = {
            "type": "standard",
            "shopper": {
                "title": self.partner_id.title or "",
                "first_name": shopper_name.get("firstName"),
                "last_name": shopper_name.get("lastName"),
                "phone": self.partner_phone or "",
                "email": self.partner_email,
                "gender": "",
                "birthdate": "",
                "billing_address": {
                    "line1": self.partner_address,
                    "line2": "",
                    "city": self.partner_city,
                    "state": self.partner_state_id.name,
                    "postal_code": self.partner_zip,
                    "country": self.partner_country_id.code,
                    "first_name": shopper_name.get("firstName"),
                    "last_name": shopper_name.get("lastName"),
                },
            },
            "order": self._prepare_order_detail(),
            "config": {"redirect_uri": redirect_url},
            "metadata": {"ref": self.reference},
        }

        return payload

    def _prepare_order_detail(self):
        order_info = self._get_order()
        order_line = None
        order = order_info.get("order")
        order_type = order_info.get("type")

        if order_type == "sale_order":
            order_line = order.order_line
        elif order_type == "invoice":
            order_line = order.invoice_line_ids

        order_detail = {
            "reference": self.reference,
            "amount": self.amount,
            "currency": self.currency_id.name,
            "shipping": {
                "pickup": True,
                "address": {
                    "line1": order.partner_shipping_id.street,
                    "line2": order.partner_shipping_id.street2 or "",
                    "city": order.partner_shipping_id.city,
                    "state": order.partner_shipping_id.state_id.name,
                    "postal_code": order.partner_shipping_id.zip,
                    "country": order.partner_shipping_id.country_code,
                },
            },
            "items": self._extract_order_lines(order_line, order_type),
        }
        return order_detail

    def _get_order(self):
        sale_order = self.env["sale.order"].search([("transaction_ids", "in", self.id)])
        inv = self.env["account.move"].search([("transaction_ids", "in", self.id)])
        if sale_order:
            return {"type": "sale_order", "order": sale_order}
        return {"type": "invoice", "order": inv}

    def _extract_order_lines(self, order_line, order_type):
        lines = []
        for l in order_line:
            qty = 0
            if order_type == "sale_order":
                qty = l.product_uom_qty
            else:
                qty = l.quantity

            lines.append(
                {
                    "name": l.product_id.name,
                    "amount": l.price_total,
                    "quantity": qty,
                    "type": "SKU",
                    "reference": l.name,
                }
            )
        return lines

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on Zip Pay data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        checkout_data = self._retrieve_zippay_checkout(notification_data.get("checkoutId"))
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "zippay" or len(tx) == 1:
            return tx

        tx = self.search([("reference", "=", checkout_data["metadata"]["ref"]), ("provider_code", "=", "zippay")])
        if not tx:
            raise ValidationError(
                "Zip Pay: " + _("No transaction found matching reference %s.", notification_data.get("ref"))
            )
        return tx

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on Zip pay data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != "zippay":
            return
        self.provider_reference = notification_data.get("checkoutId")
        payload = {
            "authority": {"type": "checkout_id", "value": notification_data.get("checkoutId")},
            "reference": self.reference,
            "amount": self.amount,
            "currency": self.currency_id.name,
            "capture": True,
            "Order": self._prepare_order_detail(),
        }

        payment_data = self.provider_id._zippay_make_request("/charges", data=payload)
        payment_status = payment_data.get("state")

        if payment_status == "pending":
            self._set_pending()
        elif payment_status in ("approved", "captured", "authorised"):
            for ss in self:
                ss._set_done()
        elif payment_status in ["expired", "canceled", "failed"]:
            self._set_canceled("Zip Pay: " + _("Canceled payment with status: %s", payment_status))
        else:
            _logger.info(
                "received data with invalid payment status (%s) for transaction with reference %s",
                payment_status,
                self.reference,
            )
            self._set_error("Zip Pay: " + _("Received data with invalid payment status: %s", payment_status))
