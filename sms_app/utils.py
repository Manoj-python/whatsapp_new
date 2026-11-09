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


from pathlib import Path
from django.conf import settings
from botocore.exceptions import ClientError
from messaging.utils import get_s3_client
from .models import SMSDocumentLink
import logging

logger = logging.getLogger(__name__)

def open_sms_pdf_from_s3(filename):
    """
    Fetch SMS PDF directly from S3.
    Does not modify or depend on open_legal_pdf().
    """

    from pathlib import Path
    from botocore.exceptions import ClientError

    filename = Path(str(filename)).name.strip()

    if not filename:
        raise ValueError("SMS PDF filename is empty")

    # Supports both "sms" and BASE_DIR / "sms"
    folder = Path(
        str(getattr(settings, "SMS_PDF_S3_FOLDER", "sms"))
    ).name

    key = f"{folder}/{filename}"

    logger.info(
        "SMS PDF S3 FETCH | bucket=%s | key=%s",
        settings.AWS_STORAGE_BUCKET_NAME,
        key,
    )

    try:
        s3 = get_s3_client()

        obj = s3.get_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
        )

        pdf_bytes = obj["Body"].read()

        logger.info(
            "SMS PDF LOADED | key=%s | size=%s",
            key,
            len(pdf_bytes),
        )

        return pdf_bytes

    except ClientError as e:
        logger.exception(
            "SMS PDF S3 FETCH FAILED | key=%s",
            key,
        )

        error_code = e.response.get("Error", {}).get("Code")

        if error_code in ("404", "NoSuchKey", "NotFound"):
            raise FileNotFoundError(
                f"SMS PDF not found in S3: {key}"
            ) from e

        raise



def generate_sms_pdf_link(mobile, filename):

    filename = Path(str(filename)).name.strip()

    if not filename or not filename.lower().endswith(".pdf"):
        raise ValueError("Invalid PDF filename.")

    s3 = get_s3_client()

    s3_key = (
        f"{settings.SMS_PDF_S3_FOLDER}/{filename}"
    )

    # Check PDF exists in private S3
    try:
        s3.head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=s3_key
        )

    except ClientError as exc:
        error_code = exc.response.get(
            "Error", {}
        ).get("Code")

        if error_code in ("404", "NoSuchKey", "NotFound"):
            raise FileNotFoundError(
                f"PDF not found in S3: {s3_key}"
            )

        raise

    # Create unique customer download token
    document = SMSDocumentLink.objects.create(
        mobile=mobile,
        s3_key=s3_key
    )

    return (
        f"{settings.SMS_PDF_BASE_URL}"
        f"?token={document.token}"
    )
