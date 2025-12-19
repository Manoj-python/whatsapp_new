# create_templates.py

import openpyxl
from django.apps import apps

MODELS = [
    "Lcc",
    "CollectionAllocation",
    "Clu",
    "Repo",
    "Paid",
    "Closed",
    "Dialer",
    "DueNotice",
    "Visiter",
    "EmployeeMaster",
    "Freshdesk",
]

def create_template(model_name):
    Model = apps.get_model("financehub", model_name)
    fields = [f.name for f in Model._meta.fields if f.name != "id" and f.name != "created_at"]

    wb = openpyxl.Workbook()
    ws = wb.active

    # Write header
    ws.append(fields)

    filename = f"{model_name}_template.xlsx"
    wb.save(filename)
    print(f"Created: {filename}")


def run():
    for m in MODELS:
        create_template(m)
