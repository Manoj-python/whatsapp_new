from messaging.models import SmsWhatsAppLog
import re

def normalize_text(s):
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()

batch_size = 5000

qs = SmsWhatsAppLog.objects.filter(normalized_text__isnull=True)

total = qs.count()
print("Total to update:", total)

processed = 0

while True:
    batch = list(qs[:batch_size])
    if not batch:
        break

    for obj in batch:
        if obj.sent_text_message:
            obj.normalized_text = normalize_text(obj.sent_text_message)[:500]
        else:
            obj.normalized_text = ""

    SmsWhatsAppLog.objects.bulk_update(batch, ["normalized_text"])

    processed += len(batch)
    print(f"Updated: {processed}/{total}")

print("DONE")
