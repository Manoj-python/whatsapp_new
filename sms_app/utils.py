import os
import urllib.parse
import urllib.request
from dataclasses import dataclass


SMS_URL = "https://api.smscountry.com/SMSCwebservice_bulk.aspx"

SMS_TIMEOUT = int(
    os.getenv("SMSCOUNTRY_TIMEOUT", "15")
)

DEFAULT_SID = "SMSQRE"


class SMSCountryConfigurationError(Exception):
    """Raised when SMSCountry configuration is missing."""


@dataclass
class SMSCountryClient:

    user: str
    password: str
    sid: str

    def __post_init__(self):
        self.opener = urllib.request.build_opener()

    def close(self):
        self.opener = None

    def send(
        self,
        mobile: str,
        message: str,
        template_id,
    ):

        mobile = str(mobile).strip()
        message = str(message)

        if not mobile:
            return False, "Mobile number is empty."

        if self.opener is None:
            return False, "SMS session is closed."

        try:

            # ----------------------------------------------
            # MESSAGE TYPE
            # ----------------------------------------------

            if contains_unicode(message):

                encoded_message = (
                    convert_to_smscountry_unicode(message)
                )

                message_type = "OL"

            else:

                encoded_message = message
                message_type = "N"

            # ----------------------------------------------
            # PARAMETERS
            # ----------------------------------------------

            params = {
                "User": self.user,
                "passwd": self.password,
                "mobilenumber": mobile,
                "message": encoded_message,
                "sid": self.sid,
                "mtype": message_type,
                "DR": "Y",
                "templateid": str(template_id),
            }

            query_string = urllib.parse.urlencode(
                params,
                encoding="utf-8",
                errors="strict",
            )

            full_url = (
                f"{SMS_URL}?{query_string}"
            )

            # ----------------------------------------------
            # REQUEST
            # ----------------------------------------------

            request = urllib.request.Request(
                full_url,
                method="GET",
                headers={
                    "User-Agent": "SMSCampaign/1.0",
                    "Accept": "text/plain",
                },
            )

            with self.opener.open(
                request,
                timeout=SMS_TIMEOUT,
            ) as response:

                result = response.read().decode(
                    "utf-8",
                    errors="replace",
                ).strip()

            # ----------------------------------------------
            # RESPONSE
            # ----------------------------------------------

            if result.startswith("OK:"):
                return True, result

            return False, result

        except Exception as exc:

            return False, str(exc)


def create_sms_session():

    user = os.getenv("SMSCOUNTRY_USER")
    password = os.getenv("SMSCOUNTRY_PASSWORD")
    sid = os.getenv(
        "SMSCOUNTRY_SID",
        DEFAULT_SID,
    )

    if not user:
        raise SMSCountryConfigurationError(
            "SMSCOUNTRY_USER environment variable is not configured."
        )

    if not password:
        raise SMSCountryConfigurationError(
            "SMSCOUNTRY_PASSWORD environment variable is not configured."
        )

    if not sid:
        raise SMSCountryConfigurationError(
            "SMSCOUNTRY_SID environment variable is not configured."
        )

    return SMSCountryClient(
        user=user,
        password=password,
        sid=sid,
    )


def contains_unicode(message) -> bool:

    return any(
        ord(char) > 127
        for char in str(message)
    )


def convert_to_smscountry_unicode(message) -> str:

    return "".join(
        f"{ord(char):04X}"
        for char in str(message)
    )


def send_sms(
    session,
    mobile,
    message,
    template_id,
):

    if session is None:
        return False, "SMS session is not initialized."

    try:

        return session.send(
            mobile=mobile,
            message=message,
            template_id=template_id,
        )

    except Exception as exc:

        return False, str(exc)