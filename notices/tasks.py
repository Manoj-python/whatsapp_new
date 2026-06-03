from celery import shared_task

@shared_task
def process_notice_task_celery(
    task_id,
    notice_type,
    excel_path,
    temp_dir
):
    # Import inside function to avoid circular import
    from .views import process_notice_task

    process_notice_task(
        task_id,
        notice_type,
        excel_path,
        temp_dir
    )
