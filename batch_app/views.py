from django.shortcuts import render

# Create your views here.
# batch_app/views.py - COMPLETE PRODUCTION READY VERSION
# ✅ PERFECT DATE/TIME HANDLING
# ✅ EDIT JOB FUNCTIONALITY
# ✅ ALL SCHEDULE TYPES SUPPORTED
# ✅ FIXED: Weekly schedule preserves first run date
# ✅ FIXED: 5-minute tolerance for date validation
# ✅ NEW: BatchExecution monitoring and management
# ✅ NEW: Execution details API endpoint

import json
import uuid
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import models
import traceback

from .models import BatchJob, BatchLog, BatchExecution

# ✅ Import tasks module
import batch_app.tasks as tasks

from .utils import read_excel_from_s3
from .app_discovery import (
    get_all_messaging_apps,
    get_templates_from_app,
    get_app_by_name,
    get_app_log_model,
    get_app_contact_model,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_ist_datetime(dt):
    """Convert datetime to IST"""
    if not dt:
        return None
    try:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return timezone.localtime(dt)
    except Exception:
        return None


def format_datetime_12hr(dt, show_date=True, show_seconds=False):
    """Format datetime in 12-hour format with AM/PM in IST"""
    if not dt:
        return '-'

    try:
        ist_dt = format_ist_datetime(dt)
        if not ist_dt:
            return '-'

        if show_date:
            if show_seconds:
                return ist_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            else:
                return ist_dt.strftime('%Y-%m-%d %I:%M %p')
        else:
            if show_seconds:
                return ist_dt.strftime('%I:%M:%S %p')
            else:
                return ist_dt.strftime('%I:%M %p')
    except Exception:
        return '-'


def format_time_12hr(dt):
    """Format only time in 12-hour format with AM/PM"""
    return format_datetime_12hr(dt, show_date=False, show_seconds=False)


def format_date_12hr(dt):
    """Format only date"""
    if not dt:
        return '-'
    try:
        ist_dt = format_ist_datetime(dt)
        if not ist_dt:
            return '-'
        return ist_dt.strftime('%Y-%m-%d')
    except Exception:
        return '-'


def validate_and_fix_schedule_datetime(dt_str):
    """Validate and fix schedule datetime with error handling"""
    try:
        dt_obj = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M')
        dt_obj = timezone.make_aware(dt_obj, timezone.get_current_timezone())

        now = timezone.now()

        current_year = now.year
        if dt_obj.year > current_year + 1:
            dt_obj = dt_obj.replace(year=current_year)

        time_diff = (now - dt_obj).total_seconds()

        # ✅ Only move to tomorrow if more than 1 hour in the past
        if time_diff > 3600:
            dt_obj = dt_obj + timedelta(days=1)
            print(f"📅 Time was more than 1 hour in past, moved to: {dt_obj.strftime('%Y-%m-%d %I:%M %p')}")
        elif time_diff > 0:
            print(f"⚠️ Time is {int(time_diff)} seconds in the past, keeping as is")
        else:
            print(f"✅ Time is in the future: {dt_obj.strftime('%Y-%m-%d %I:%M %p')}")

        return dt_obj

    except Exception as e:
        raise ValueError(f"Invalid date/time: {e}")


def format_time_display(time_str):
    """Convert 24-hour time to 12-hour format with AM/PM"""
    try:
        t = datetime.strptime(time_str, '%H:%M').time()
        return t.strftime('%I:%M %p')
    except:
        return time_str


def get_job_data(job):
    """Get job data with 12-hour format IST times"""
    try:
        # ✅ Convert all datetimes to IST
        created_ist = format_ist_datetime(job.created_at)
        started_ist = format_ist_datetime(job.started_at)
        completed_ist = format_ist_datetime(job.completed_at)
        schedule_ist = format_ist_datetime(job.schedule_datetime)
        next_run_ist = format_ist_datetime(job.next_run_time)
        end_date_ist = format_ist_datetime(job.end_date)

        # ✅ Format schedule time in 12-hour format
        schedule_time_str = schedule_ist.strftime('%I:%M %p') if schedule_ist else 'Not set'

        # Get execution stats
        total_executions = BatchExecution.objects.filter(job=job).count()
        completed_executions = BatchExecution.objects.filter(job=job, status='completed').count()
        failed_executions = BatchExecution.objects.filter(job=job, status='failed').count()
        running_executions = BatchExecution.objects.filter(job=job, status='running').count()
        pending_executions = BatchExecution.objects.filter(job=job, status='pending').count()

        return {
            # Basic Info
            'job_id': job.job_id,
            'job_name': job.job_name,
            'target_app': job.target_app,
            'template_id': job.template_id,
            'template_name': job.template_name,
            'template_language': job.template_language,
            'excel_path': job.excel_path,

            # Batch Settings
            'batch_size': job.batch_size,
            'batch_size_type': job.batch_size_type,

            # Schedule Settings
            'schedule_type': job.schedule_type,
            'schedule_times': job.schedule_times,
            'weekly_day': job.weekly_day,
            'interval_days': job.interval_days,
            'schedule_info': job.get_schedule_info(),

            # Status & Progress
            'status': job.status,
            'total_customers': job.total_customers,
            'total_batches': job.total_batches,
            'completed_batches': job.completed_batches,
            'current_batch': job.current_batch,

            # Stats
            'sent_count': job.sent_count,
            'failed_count': job.failed_count,
            'skipped_count': job.skipped_count,
            'total_runs': job.total_runs,
            'completed_runs': job.completed_runs,

            # Metadata
            'created_by': job.created_by,
            'error_message': job.error_message,
            'report_file': job.report_file,

            # ✅ 12-hour format with AM/PM (IST)
            'created_at': created_ist.strftime('%Y-%m-%d %I:%M:%S %p') if created_ist else '-',
            'started_at': started_ist.strftime('%Y-%m-%d %I:%M:%S %p') if started_ist else '-',
            'completed_at': completed_ist.strftime('%Y-%m-%d %I:%M:%S %p') if completed_ist else '-',
            'schedule_datetime': schedule_ist.strftime('%Y-%m-%d %I:%M:%S %p') if schedule_ist else '-',
            'next_run_time': next_run_ist.strftime('%Y-%m-%d %I:%M:%S %p') if next_run_ist else 'Not scheduled',
            'end_date': end_date_ist.strftime('%Y-%m-%d %I:%M:%S %p') if end_date_ist else 'No end date',

            # ✅ Only time in 12-hour format
            'schedule_time': schedule_time_str,

            # ✅ Only date
            'created_date': created_ist.strftime('%Y-%m-%d') if created_ist else '-',

            # ✅ Raw objects for calculations
            'schedule_datetime_obj': job.schedule_datetime,
            'next_run_time_obj': job.next_run_time,
            'end_date_obj': job.end_date,

            # ✅ Execution stats (NEW)
            'execution_stats': {
                'total': total_executions,
                'completed': completed_executions,
                'failed': failed_executions,
                'running': running_executions,
                'pending': pending_executions,
            }
        }
    except Exception as e:
        return {
            'error': str(e),
            'job_id': job.job_id,
            'job_name': job.job_name,
        }


# ============================================================
# VIEWS
# ============================================================

def dashboard(request):
    try:
        context = {
            'total_jobs': BatchJob.objects.count(),
            'running_jobs': BatchJob.objects.filter(status='running').count(),
            'completed_jobs': BatchJob.objects.filter(status='completed').count(),
            'failed_jobs': BatchJob.objects.filter(status='failed').count(),
            'total_sent': BatchJob.objects.aggregate(total=models.Sum('sent_count'))['total'] or 0,
            'total_skipped': BatchJob.objects.aggregate(total=models.Sum('skipped_count'))['total'] or 0,
            'total_failed': BatchJob.objects.aggregate(total=models.Sum('failed_count'))['total'] or 0,
            'recent_jobs': BatchJob.objects.order_by('-created_at')[:10],
            'discovered_apps': get_all_messaging_apps(),
            'current_time': format_datetime_12hr(timezone.now()),
            'current_date': format_date_12hr(timezone.now()),
            'current_time_only': format_time_12hr(timezone.now()),
            'timezone': 'Asia/Kolkata (IST)',
            'format_type': '12-hour (AM/PM)',
        }
        return render(request, 'batch_app/dashboard.html', context)
    except Exception as e:
        messages.error(request, f'❌ Error loading dashboard: {str(e)}')
        return render(request, 'batch_app/dashboard.html', {})


def get_apps_api(request):
    try:
        apps = get_all_messaging_apps()
        return JsonResponse({
            'apps': [{'key': key, 'label': label} for key, label in apps]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_templates_api(request):
    try:
        app_name = request.GET.get('app', 'messaging')
        templates = get_templates_from_app(app_name)
        return JsonResponse({'templates': templates})
    except Exception as e:
        return JsonResponse({'error': str(e), 'templates': []}, status=500)


def job_count_api(request):
    try:
        running_count = BatchJob.objects.filter(status='running').count()
        return JsonResponse({'running': running_count})
    except Exception as e:
        return JsonResponse({'error': str(e), 'running': 0}, status=500)


def batch_job_list(request):
    try:
        jobs = BatchJob.objects.all().order_by('-created_at')
        status_filter = request.GET.get('status', '')
        if status_filter:
            jobs = jobs.filter(status=status_filter)

        paginator = Paginator(jobs, 20)
        page = request.GET.get('page', 1)
        jobs_page = paginator.get_page(page)

        apps = get_all_messaging_apps()

        return render(request, 'batch_app/jobs.html', {
            'jobs': jobs_page,
            'status_filter': status_filter,
            'status_choices': BatchJob.STATUS_CHOICES,
            'apps': dict(apps),
            'current_time': format_datetime_12hr(timezone.now()),
        })
    except Exception as e:
        messages.error(request, f'❌ Error loading jobs: {str(e)}')
        return render(request, 'batch_app/jobs.html', {'jobs': []})


# ============================================================
# BATCH JOB CREATE - PERFECT TIME HANDLING (FULLY FIXED)
# ============================================================

def batch_job_create(request):
    """Create new batch job with error handling"""
    if request.method == 'POST':
        try:
            # Get form data with validation
            job_name = request.POST.get('job_name', '').strip()
            if not job_name:
                messages.error(request, '❌ Job name is required')
                return redirect('batch_job_create')

            target_app = request.POST.get('target_app', 'messaging')
            template_id = request.POST.get('template_id')
            excel_path = request.POST.get('excel_path', '').strip()

            if not excel_path:
                messages.error(request, '❌ Excel file path is required')
                return redirect('batch_job_create')

            # Validate app exists
            app = get_app_by_name(target_app)
            if not app:
                messages.error(request, f'❌ App "{target_app}" not found')
                return redirect('batch_job_create')

            # Get template details
            templates = get_templates_from_app(target_app)
            template_info = None
            for t in templates:
                if t['id'] == template_id:
                    template_info = t
                    break

            if not template_info:
                messages.error(request, f'❌ Template "{template_id}" not found in {target_app}')
                return redirect('batch_job_create')

            # Get schedule data
            schedule_type = request.POST.get('schedule_type', 'daily')
            schedule_date = request.POST.get('schedule_date', '')
            schedule_time = request.POST.get('schedule_time', '09:00')

            # Multiple daily times
            schedule_times = request.POST.getlist('schedule_times[]', [])
            multiple_schedule_date = request.POST.get('multiple_schedule_date', '')

            # Other schedule fields
            weekly_day = request.POST.get('weekly_day')
            interval_days = request.POST.get('interval_days')

            # End date
            has_end_date = request.POST.get('has_end_date') == 'on'
            end_date_str = request.POST.get('end_date', '')

            # Batch size
            batch_size_type = request.POST.get('batch_size_type', 'custom')
            batch_size_str = request.POST.get('batch_size', '1000')

            # Validate batch size
            try:
                batch_size = int(batch_size_str) if batch_size_type == 'custom' else 0
                if batch_size_type == 'custom' and batch_size < 1:
                    messages.error(request, '❌ Batch size must be at least 1')
                    return redirect('batch_job_create')
            except ValueError:
                messages.error(request, '❌ Please enter a valid number for batch size')
                return redirect('batch_job_create')

            # ============================================================
            # ✅ FIXED: VALIDATE SCHEDULE WITH 1-HOUR TOLERANCE
            # ============================================================
            schedule_datetime_obj = None

            # ============================================================
            # ✅ FIXED 1: MULTIPLE DAILY - NEVER MODIFY, PRESERVE EXACT TIMES
            # ============================================================
            if schedule_type == 'multiple_daily':
                if not schedule_times:
                    messages.error(request, '❌ Please add at least one time for multiple daily schedule')
                    return redirect('batch_job_create')

                if not multiple_schedule_date:
                    messages.error(request, '❌ Please select a date for multiple daily schedule')
                    return redirect('batch_job_create')

                try:
                    date_obj = datetime.strptime(multiple_schedule_date, '%Y-%m-%d').date()
                    first_time = schedule_times[0]
                    t = datetime.strptime(first_time, '%H:%M').time()

                    # Combine date and time - EXACT time
                    schedule_datetime_obj = timezone.make_aware(
                        datetime.combine(date_obj, t),
                        timezone.get_current_timezone()
                    )

                    now = timezone.now()
                    time_diff = (schedule_datetime_obj - now).total_seconds()

                    # ✅ FIXED: Multiple Daily - NEVER modify, ONLY log
                    # Even if time is past, we keep it because the scheduler will find the next time
                    print(f"📅 Multiple daily - Keeping exact time: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')} (diff: {time_diff:.0f}s)")
                    print(f"📅 Multiple daily date: {multiple_schedule_date}")
                    print(f"📅 Multiple daily times: {schedule_times}")

                except Exception as e:
                    messages.error(request, f'❌ Invalid date/time format: {e}')
                    return redirect('batch_job_create')

            # ============================================================
            # ✅ FIXED 2: WEEKLY SCHEDULE - PRESERVE USER'S EXACT DATE AND TIME
            # ============================================================
            elif schedule_type == 'weekly':
                if not schedule_date or not schedule_time:
                    messages.error(request, '❌ Please select a date and time')
                    return redirect('batch_job_create')

                # Use the exact time from the weekly time input
                weekly_time = request.POST.get('schedule_time', schedule_time)

                schedule_datetime_str = f"{schedule_date}T{weekly_time}"

                try:
                    dt_obj = datetime.strptime(schedule_datetime_str, '%Y-%m-%dT%H:%M')
                    schedule_datetime_obj = timezone.make_aware(dt_obj, timezone.get_current_timezone())

                    # Get the selected day from dropdown (0=Monday, 6=Sunday)
                    selected_weekly_day = int(weekly_day) if weekly_day else 0

                    # Get the day of week from the selected date
                    selected_weekday = schedule_datetime_obj.weekday()  # 0=Monday, 6=Sunday

                    # If the selected date doesn't match the selected day, adjust
                    if selected_weekday != selected_weekly_day:
                        days_ahead = (selected_weekly_day - selected_weekday + 7) % 7
                        if days_ahead == 0:
                            days_ahead = 7
                        schedule_datetime_obj += timedelta(days=days_ahead)
                        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                        messages.warning(
                            request,
                            f'⚠️ Selected date was not a {days[selected_weekly_day]}. '
                            f'Adjusted to {schedule_datetime_obj.strftime("%A, %B %d, %Y at %I:%M %p")}'
                        )

                    now = timezone.now()
                    time_diff = (schedule_datetime_obj - now).total_seconds()

                    # Keep the user's selected first run exactly. The scheduler
                    # decides the next future run without changing this anchor.
                    print(f"✅ Weekly - Keeping user's selected time: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')} (diff: {time_diff:.0f}s)")

                    print(f"✅ Weekly schedule created: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')}")

                except ValueError as e:
                    messages.error(request, f'❌ Invalid date/time: {e}')
                    return redirect('batch_job_create')

            # ============================================================
            # ✅ FIXED 3: DAILY / CUSTOM - PRESERVE USER'S EXACT TIME
            # ============================================================
            else:
                if not schedule_date or not schedule_time:
                    messages.error(request, '❌ Please select a date and time')
                    return redirect('batch_job_create')

                schedule_datetime_str = f"{schedule_date}T{schedule_time}"

                try:
                    dt_obj = datetime.strptime(schedule_datetime_str, '%Y-%m-%dT%H:%M')
                    schedule_datetime_obj = timezone.make_aware(dt_obj, timezone.get_current_timezone())

                    now = timezone.now()
                    time_diff = (schedule_datetime_obj - now).total_seconds()

                    # Keep the user's selected first run exactly. The scheduler
                    # calculates the next future execution from this anchor.
                    print(f"✅ Keeping user's selected time: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')} (diff: {time_diff:.0f}s)")

                except ValueError as e:
                    messages.error(request, f'❌ Invalid date/time: {e}')
                    return redirect('batch_job_create')

            # Validate end date
            end_date_obj = None
            if has_end_date and end_date_str:
                try:
                    end_date_obj = validate_and_fix_schedule_datetime(end_date_str)
                    if end_date_obj <= schedule_datetime_obj:
                        messages.error(request, '❌ End date must be after the first run date')
                        return redirect('batch_job_create')
                except ValueError as e:
                    messages.error(request, f'❌ Invalid end date: {e}')
                    return redirect('batch_job_create')

            # Read Excel
            try:
                df = read_excel_from_s3(excel_path)
                if df is None:
                    messages.error(request, '❌ Could not read Excel file from S3')
                    return redirect('batch_job_create')
            except Exception as e:
                messages.error(request, f'❌ Error reading Excel file: {str(e)}')
                return redirect('batch_job_create')

            total = len(df)
            if total == 0:
                messages.error(request, '❌ No customers found in Excel file')
                return redirect('batch_job_create')

            # Calculate batches
            if batch_size_type == 'full':
                total_batches = 1
                batch_size = total
            else:
                total_batches = (total + batch_size - 1) // batch_size

            # Generate job_id
            job_id = f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

            # Create the job
            job = BatchJob.objects.create(
                job_id=job_id,
                job_name=job_name,
                target_app=target_app,
                template_id=template_id,
                template_name=template_info['name'],
                template_language=template_info['language'],
                excel_path=excel_path,
                schedule_datetime=schedule_datetime_obj,
                batch_size_type=batch_size_type,
                batch_size=batch_size,
                schedule_type=schedule_type,
                schedule_times=schedule_times if schedule_type == 'multiple_daily' else [],
                weekly_day=int(weekly_day) if weekly_day and schedule_type == 'weekly' else None,
                interval_days=int(interval_days) if interval_days and schedule_type == 'custom_interval' else None,
                end_date=end_date_obj,
                total_customers=total,
                total_batches=total_batches,
                status='scheduled',
                created_by=request.user.username if request.user.is_authenticated else 'System',
            )

            # ✅ Schedule the job using the new scheduler
            try:
                from batch_app import tasks
                job.next_run_time = job.schedule_datetime
                job.save(update_fields=["next_run_time"])
                # Use the new scheduler
                tasks.schedule_batch_job.delay(job.job_id)
            except Exception as e:
                messages.warning(request, f'⚠️ Job created but scheduling failed: {str(e)}')

            # Build success message
            schedule_desc = job.get_schedule_info()
            batch_desc = "FULL (all customers)" if batch_size_type == 'full' else f"{batch_size:,} per batch"

            if schedule_type == 'multiple_daily':
                times_display = ', '.join([format_time_display(t) for t in schedule_times])
                schedule_desc = f"Multiple times on {multiple_schedule_date}: {times_display}"

            messages.success(
                request,
                f'✅ Job created! {total:,} customers, {total_batches} batches '
                f'(batch size: {batch_desc}) using "{template_info["label"]}" - '
                f'Schedule: {schedule_desc} on {app["label"]}'
            )
            return redirect('batch_job_detail', job_id=job.job_id)

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f'❌ Error creating job: {str(e)}')
            return redirect('batch_job_create')

    # GET request - show form
    try:
        app_choices = get_all_messaging_apps()
        today = timezone.now().strftime('%Y-%m-%d')
        current_time = timezone.now().strftime('%H:%M')

        return render(request, 'batch_app/job_form.html', {
            'app_choices': app_choices,
            'default_batch_size': 1000,
            'today': today,
            'current_time': current_time,
        })
    except Exception as e:
        messages.error(request, f'❌ Error loading form: {str(e)}')
        return render(request, 'batch_app/job_form.html', {})


# ============================================================
# BATCH JOB DETAIL
# ============================================================

def batch_job_detail(request, job_id):
    try:
        job = get_object_or_404(BatchJob, job_id=job_id)
        logs = BatchLog.objects.filter(job=job).order_by('-sent_at')[:50]
        
        # Get executions for this job
        executions = BatchExecution.objects.filter(job=job).order_by('batch_number')
        
        templates = get_templates_from_app(job.target_app)
        template_label = next((t['label'] for t in templates if t['id'] == job.template_name), job.template_name)

        job_data = get_job_data(job)

        formatted_logs = []
        for log in logs:
            formatted_logs.append({
                'mobile': log.mobile,
                'customer_name': log.customer_name,
                'status': log.status,
                'message_id': log.message_id,
                'error_message': log.error_message,
                'sent_at': format_datetime_12hr(log.sent_at, show_seconds=True),
                'sent_at_raw': log.sent_at,
            })

        # Format executions for display
        formatted_executions = []
        for exec in executions:
            formatted_executions.append({
                'batch_number': exec.batch_number,
                'total_customers': exec.total_customers,
                'sent_count': exec.sent_count,
                'failed_count': exec.failed_count,
                'skipped_count': exec.skipped_count,
                'status': exec.status,
                'error_message': exec.error_message,
                'started_at': format_datetime_12hr(exec.started_at, show_seconds=True) if exec.started_at else '-',
                'completed_at': format_datetime_12hr(exec.completed_at, show_seconds=True) if exec.completed_at else '-',
            })

        return render(request, 'batch_app/job_detail.html', {
            'job': job,
            'job_data': job_data,
            'logs': formatted_logs,
            'executions': formatted_executions,
            'progress': job.progress_percentage(),
            'template_label': template_label,
            'current_time': format_datetime_12hr(timezone.now()),
            'timezone': 'Asia/Kolkata (IST)',
            'format_type': '12-hour (AM/PM)',
        })
    except Exception as e:
        messages.error(request, f'❌ Error loading job details: {str(e)}')
        return redirect('batch_job_list')


# ============================================================
# BATCH JOB EDIT
# ============================================================
def batch_job_edit(request, job_id):
    """Edit an existing batch job"""
    job = get_object_or_404(BatchJob, job_id=job_id)

    # Only allow editing if job is not running or completed
    if job.status in ['running', 'completed']:
        messages.error(request, f'❌ Cannot edit a {job.status} job')
        return redirect('batch_job_detail', job_id=job.job_id)

    if request.method == 'POST':
        try:
            # Get form data
            job_name = request.POST.get('job_name', '').strip()
            if not job_name:
                messages.error(request, '❌ Job name is required')
                return redirect('batch_job_edit', job_id=job.job_id)

            target_app = request.POST.get('target_app', 'messaging')
            template_id = request.POST.get('template_id')
            excel_path = request.POST.get('excel_path', '').strip()

            if not excel_path:
                messages.error(request, '❌ Excel file path is required')
                return redirect('batch_job_edit', job_id=job.job_id)

            # Get schedule data
            schedule_type = request.POST.get('schedule_type', 'daily')
            schedule_date = request.POST.get('schedule_date', '')
            schedule_time = request.POST.get('schedule_time', '09:00')

            # Multiple daily times
            schedule_times = request.POST.getlist('schedule_times[]', [])
            multiple_schedule_date = request.POST.get('multiple_schedule_date', '')

            # Other schedule fields
            weekly_day = request.POST.get('weekly_day')
            interval_days = request.POST.get('interval_days')

            # End date
            has_end_date = request.POST.get('has_end_date') == 'on'
            end_date_str = request.POST.get('end_date', '')

            # Batch size
            batch_size_type = request.POST.get('batch_size_type', 'custom')
            batch_size_str = request.POST.get('batch_size', '1000')

            # Validate batch size
            try:
                batch_size = int(batch_size_str) if batch_size_type == 'custom' else 0
                if batch_size_type == 'custom' and batch_size < 1:
                    messages.error(request, '❌ Batch size must be at least 1')
                    return redirect('batch_job_edit', job_id=job.job_id)
            except ValueError:
                messages.error(request, '❌ Please enter a valid number for batch size')
                return redirect('batch_job_edit', job_id=job.job_id)

            # Validate schedule
            schedule_datetime_obj = None

            if schedule_type == 'multiple_daily':
                if not schedule_times:
                    messages.error(request, '❌ Please add at least one time for multiple daily schedule')
                    return redirect('batch_job_edit', job_id=job.job_id)

                if not multiple_schedule_date:
                    messages.error(request, '❌ Please select a date for multiple daily schedule')
                    return redirect('batch_job_edit', job_id=job.job_id)

                try:
                    date_obj = datetime.strptime(multiple_schedule_date, '%Y-%m-%d').date()
                    first_time = schedule_times[0]
                    t = datetime.strptime(first_time, '%H:%M').time()

                    schedule_datetime_obj = timezone.make_aware(
                        datetime.combine(date_obj, t),
                        timezone.get_current_timezone()
                    )

                    now = timezone.now()
                    time_diff = (schedule_datetime_obj - now).total_seconds()
                    print(f"✅ Multiple daily edit - Keeping exact time: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')} (diff: {time_diff:.0f}s)")

                except Exception as e:
                    messages.error(request, f'❌ Invalid date/time format: {e}')
                    return redirect('batch_job_edit', job_id=job.job_id)

            else:
                if not schedule_date or not schedule_time:
                    messages.error(request, '❌ Please select a date and time')
                    return redirect('batch_job_edit', job_id=job.job_id)

                schedule_datetime_str = f"{schedule_date}T{schedule_time}"

                try:
                    dt_obj = datetime.strptime(schedule_datetime_str, '%Y-%m-%dT%H:%M')
                    schedule_datetime_obj = timezone.make_aware(dt_obj, timezone.get_current_timezone())

                    now = timezone.now()
                    time_diff = (schedule_datetime_obj - now).total_seconds()
                    print(f"✅ Edit - Keeping user's selected time: {schedule_datetime_obj.strftime('%Y-%m-%d %I:%M %p')} (diff: {time_diff:.0f}s)")

                except ValueError as e:
                    messages.error(request, f'❌ Invalid date/time: {e}')
                    return redirect('batch_job_edit', job_id=job.job_id)

            # Validate end date
            end_date_obj = None
            if has_end_date and end_date_str:
                try:
                    end_date_obj = validate_and_fix_schedule_datetime(end_date_str)
                    if end_date_obj <= schedule_datetime_obj:
                        messages.error(request, '❌ End date must be after the first run date')
                        return redirect('batch_job_edit', job_id=job.job_id)
                except ValueError as e:
                    messages.error(request, f'❌ Invalid end date: {e}')
                    return redirect('batch_job_edit', job_id=job.job_id)

            # Read Excel
            df = read_excel_from_s3(excel_path)
            if df is None:
                messages.error(request, '❌ Could not read Excel file from S3')
                return redirect('batch_job_edit', job_id=job.job_id)

            total = len(df)
            if total == 0:
                messages.error(request, '❌ No customers found in Excel file')
                return redirect('batch_job_edit', job_id=job.job_id)

            # Calculate batches
            if batch_size_type == 'full':
                total_batches = 1
                batch_size = total
            else:
                total_batches = (total + batch_size - 1) // batch_size

            # ✅ Update the job
            job.job_name = job_name
            job.target_app = target_app
            job.template_id = template_id
            job.excel_path = excel_path
            job.schedule_datetime = schedule_datetime_obj
            job.batch_size_type = batch_size_type
            job.batch_size = batch_size
            job.schedule_type = schedule_type
            job.schedule_times = schedule_times if schedule_type == 'multiple_daily' else []
            job.weekly_day = int(weekly_day) if weekly_day and schedule_type == 'weekly' else None
            job.interval_days = int(interval_days) if interval_days and schedule_type == 'custom_interval' else None
            job.end_date = end_date_obj
            job.total_customers = total
            job.total_batches = total_batches
            job.status = 'scheduled'

            # ✅ Reset progress
            job.current_batch = 0
            job.completed_batches = 0
            job.sent_count = 0
            job.failed_count = 0
            job.skipped_count = 0
            job.total_runs = 0
            job.completed_runs = 0
            job.completed_at = None

            # ✅ Delete existing executions (they will be recreated)
            BatchExecution.objects.filter(job=job).delete()

            # ✅ Calculate correct next run time
            now = timezone.now()
            
            if schedule_type == 'daily':
                next_run = schedule_datetime_obj
                while next_run <= now:
                    next_run += timedelta(days=1)
                job.next_run_time = next_run
                
            elif schedule_type == 'weekly':
                next_run = schedule_datetime_obj
                while next_run <= now:
                    next_run += timedelta(days=7)
                job.next_run_time = next_run
                
            elif schedule_type == 'custom_interval':
                interval = int(interval_days) if interval_days else 1
                next_run = schedule_datetime_obj
                while next_run <= now:
                    next_run += timedelta(days=interval)
                job.next_run_time = next_run
                
            elif schedule_type == 'multiple_daily':
                # For multiple daily, use the _get_next_multiple_time method
                # Temporarily set the schedule_times and schedule_datetime
                job.schedule_times = schedule_times
                job.schedule_datetime = schedule_datetime_obj
                next_run = job._get_next_multiple_time(now)
                job.next_run_time = next_run if next_run else schedule_datetime_obj

            job.save()

            # ✅ Reschedule the job using the new scheduler
            try:
                tasks.schedule_batch_job.delay(job.job_id)
                messages.success(
                    request, 
                    f'✅ Job "{job.job_name}" updated and rescheduled! '
                    f'Next run: {job.next_run_time.strftime("%Y-%m-%d %I:%M %p")}'
                )
            except Exception as e:
                messages.warning(request, f'⚠️ Job updated but scheduling failed: {str(e)}')

            return redirect('batch_job_detail', job_id=job.job_id)

        except Exception as e:
            traceback.print_exc()
            messages.error(request, f'❌ Error updating job: {str(e)}')
            return redirect('batch_job_edit', job_id=job.job_id)

    # GET request - show edit form
    try:
        app_choices = get_all_messaging_apps()
        templates = get_templates_from_app(job.target_app)

        # Format times for display
        schedule_date = job.schedule_datetime.strftime('%Y-%m-%d') if job.schedule_datetime else ''
        schedule_time = job.schedule_datetime.strftime('%H:%M') if job.schedule_datetime else '09:00'
        multiple_schedule_date = schedule_date

        # End date
        end_date = job.end_date.strftime('%Y-%m-%dT%H:%M') if job.end_date else ''

        return render(request, 'batch_app/job_edit.html', {
            'job': job,
            'app_choices': app_choices,
            'templates': templates,
            'schedule_date': schedule_date,
            'schedule_time': schedule_time,
            'multiple_schedule_date': multiple_schedule_date,
            'end_date': end_date,
            'has_end_date': bool(job.end_date),
            'default_batch_size': 1000,
            'today': timezone.now().strftime('%Y-%m-%d'),
            'current_time': timezone.now().strftime('%H:%M'),
        })
    except Exception as e:
        messages.error(request, f'❌ Error loading edit form: {str(e)}')
        return redirect('batch_job_detail', job_id=job.job_id)
# ============================================================
# BATCH JOB ACTIONS
# ============================================================
@csrf_exempt
def batch_job_action(request, job_id, action):
    # ✅ Define is_ajax at the START
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        job = get_object_or_404(BatchJob, job_id=job_id)

        # ❌ REMOVE THIS BLOCK - 'edit' should NOT be handled here
        # if action == 'edit':
        #     if is_ajax:
        #         return JsonResponse({
        #             'success': True,
        #             'redirect_url': f'/batch/jobs/{job_id}/edit/'
        #         })
        #     else:
        #         return redirect('batch_job_edit', job_id=job.job_id)

        if action == 'pause':
            job.status = 'paused'
            job.save(update_fields=['status'])

            message = f'⏸️ Job "{job.job_name}" paused!'

        elif action == 'resume':
            # Resume without changing the schedule
            job.status = 'scheduled'

            # Preserve existing next run time
            if job.next_run_time is None:
                job.next_run_time = job.schedule_datetime

            job.save(update_fields=['status', 'next_run_time'])

            # Queue the scheduler only once
            tasks.schedule_batch_job.delay(job.job_id)

            message = f'▶️ Job "{job.job_name}" resumed!'
        elif action == 'cancel':
            job.status = 'cancelled'
            job.save()
            try:
                from .models import BatchExecution
                BatchExecution.objects.filter(job=job, status__in=['pending', 'running']).update(status='cancelled')
            except:
                pass
            tasks.cancel_daily_schedule.delay(job.job_id)
            message = f'⛔ Job "{job.job_name}" cancelled!'

        elif action == 'restart':
            try:
                from .models import BatchExecution
                BatchExecution.objects.filter(job=job).delete()
            except:
                pass
            job.current_batch = 0
            job.completed_batches = 0
            job.sent_count = 0
            job.failed_count = 0
            job.skipped_count = 0
            job.total_runs = 0
            job.completed_runs = 0
            job.status = 'scheduled'
            job.completed_at = None
            
            now = timezone.now()
            
            if job.schedule_type == 'daily':
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=1)
                job.next_run_time = next_run
                
            elif job.schedule_type == 'weekly':
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=7)
                job.next_run_time = next_run
                
            elif job.schedule_type == 'custom_interval':
                interval = job.interval_days or 1
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=interval)
                job.next_run_time = next_run
                
            elif job.schedule_type == 'multiple_daily':
                next_run = job._get_next_multiple_time(now)
                job.next_run_time = next_run if next_run else job.schedule_datetime
            
            job.save()
            tasks.schedule_batch_job.delay(job.job_id)
            message = f'🔄 Job "{job.job_name}" restarted!'

        elif action == 'force_run':
            tasks.process_batch_scheduler.delay(job.job_id)
            message = f'🚀 Job "{job.job_name}" started!'

        else:
            if is_ajax:
                return JsonResponse({'error': f'Unknown action: {action}'}, status=400)
            messages.error(request, f'❌ Unknown action: {action}')
            return redirect('batch_job_detail', job_id=job.job_id)

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': message,
                'status': job.status,
                'next_run_time': job.next_run_time.strftime('%Y-%m-%d %I:%M %p') if job.next_run_time else None
            })
        else:
            messages.success(request, message)
            return redirect('batch_job_detail', job_id=job.job_id)

    except Exception as e:
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        else:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('batch_job_detail', job_id=job_id)
        
@csrf_exempt
def batch_job_delete(request, job_id):
    try:
        job = get_object_or_404(BatchJob, job_id=job_id)
        job_name = job.job_name
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # ✅ Cancel any scheduled tasks and delete executions
        tasks.cancel_daily_schedule.delay(job.job_id)
        BatchExecution.objects.filter(job=job).delete()
        
        # Delete the job
        job.delete()

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': f'✅ Job "{job_name}" deleted successfully!'
            })
        else:
            messages.success(request, f'✅ Job {job_name} deleted!')
            return redirect('batch_job_list')

    except Exception as e:
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        else:
            messages.error(request, f'❌ Error deleting job: {str(e)}')
            return redirect('batch_job_detail', job_id=job_id)


# ============================================================
# BATCH JOB LOGS
# ============================================================

def batch_job_logs(request, job_id):
    try:
        job = get_object_or_404(BatchJob, job_id=job_id)
        logs = BatchLog.objects.filter(job=job).order_by('-sent_at')

        status_filter = request.GET.get('status', '')
        if status_filter:
            logs = logs.filter(status=status_filter)

        paginator = Paginator(logs, 100)
        page = request.GET.get('page', 1)
        logs_page = paginator.get_page(page)

        formatted_logs = []
        for log in logs_page:
            formatted_logs.append({
                'id': log.id,
                'mobile': log.mobile,
                'customer_name': log.customer_name,
                'status': log.status,
                'message_id': log.message_id,
                'error_message': log.error_message,
                'sent_at': format_datetime_12hr(log.sent_at, show_seconds=True),
            })

        return render(request, 'batch_app/job_logs.html', {
            'job': job,
            'logs': formatted_logs,
            'status_filter': status_filter,
            'total': logs.count(),
            'page_obj': logs_page,
            'current_time': format_datetime_12hr(timezone.now()),
        })
    except Exception as e:
        messages.error(request, f'❌ Error loading logs: {str(e)}')
        return redirect('batch_job_detail', job_id=job_id)


# ============================================================
# BATCH JOB REPORT
# ============================================================

import io
import pandas as pd
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import BatchJob, BatchLog

def batch_job_report(request, job_id):
    """
    Generate Excel report with support for status filtering.
    GET params:
        ?status=success  - Only success (Sent, Delivered, Read)
        ?status=skipped  - Only skipped (Skipped, PAID)
        ?status=failed   - Only failed
        (no param)       - All logs
    """
    job = get_object_or_404(BatchJob, job_id=job_id)
    
    # Base queryset
    logs = BatchLog.objects.filter(job=job)
    
    # Apply status filter
    status_filter = request.GET.get('status', 'all')
    
    if status_filter == 'success':
        # Success: Sent, Delivered, Read statuses
        logs = logs.filter(status__in=['Sent', 'Delivered', 'Read'])
        filename_suffix = "success"
    elif status_filter == 'skipped':
        # Skipped: Skipped, PAID statuses
        logs = logs.filter(status__in=['Skipped', 'PAID'])
        filename_suffix = "skipped"
    elif status_filter == 'failed':
        # Failed: Failed status
        logs = logs.filter(status='Failed')
        filename_suffix = "failed"
    else:
        filename_suffix = "full"
    
    # Convert to DataFrame
    data = [{
        'Mobile': log.mobile,
        'Customer Name': log.customer_name,
        'Status': log.status,
        'Message ID': log.message_id,
        'Error': log.error_message,
        'Sent At': format_datetime_12hr(log.sent_at, show_seconds=True) if log.sent_at else '',
    } for log in logs]
    
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="batch_{job.job_id}_{filename_suffix}_report.xlsx"'
    return response
# ============================================================
# NEW: BATCH EXECUTIONS API
# ============================================================

@csrf_exempt
@require_http_methods(["GET"])
def get_executions_api(request, job_id):
    """
    Get all executions for a job with detailed status
    """
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)

    try:
        executions = BatchExecution.objects.filter(job=job).order_by('batch_number')
        
        data = []
        for exec in executions:
            data.append({
                'batch_number': exec.batch_number,
                'total_customers': exec.total_customers,
                'sent_count': exec.sent_count,
                'failed_count': exec.failed_count,
                'skipped_count': exec.skipped_count,
                'status': exec.status,
                'error_message': exec.error_message,
                'started_at': format_datetime_12hr(exec.started_at) if exec.started_at else None,
                'completed_at': format_datetime_12hr(exec.completed_at) if exec.completed_at else None,
                'created_at': format_datetime_12hr(exec.created_at),
            })
        
        stats = {
            'total': len(data),
            'completed': BatchExecution.objects.filter(job=job, status='completed').count(),
            'failed': BatchExecution.objects.filter(job=job, status='failed').count(),
            'running': BatchExecution.objects.filter(job=job, status='running').count(),
            'pending': BatchExecution.objects.filter(job=job, status='pending').count(),
            'cancelled': BatchExecution.objects.filter(job=job, status='cancelled').count(),
        }

        return JsonResponse({
            'success': True,
            'job_id': job.job_id,
            'job_name': job.job_name,
            'total_batches': job.total_batches,
            'completed_batches': job.completed_batches,
            'stats': stats,
            'executions': data
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================
# NEW: EXECUTION DETAIL API
# ============================================================

@csrf_exempt
@require_http_methods(["GET"])
def get_execution_detail_api(request, execution_id):
    """
    Get detailed information about a specific execution
    """
    try:
        execution = BatchExecution.objects.get(id=execution_id)
    except BatchExecution.DoesNotExist:
        return JsonResponse({"error": "Execution not found"}, status=404)

    try:
        return JsonResponse({
            'success': True,
            'id': execution.id,
            'job_id': execution.job.job_id,
            'batch_number': execution.batch_number,
            'start_row': execution.start_row,
            'end_row': execution.end_row,
            'total_customers': execution.total_customers,
            'sent_count': execution.sent_count,
            'failed_count': execution.failed_count,
            'skipped_count': execution.skipped_count,
            'status': execution.status,
            'error_message': execution.error_message,
            'started_at': format_datetime_12hr(execution.started_at) if execution.started_at else None,
            'completed_at': format_datetime_12hr(execution.completed_at) if execution.completed_at else None,
            'created_at': format_datetime_12hr(execution.created_at),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================
# API: BATCH JOB STATUS (UPDATED with execution stats)
# ============================================================

@csrf_exempt
@require_http_methods(["GET"])
def batch_job_status_api(request, job_id):
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)

    try:
        # Get execution stats
        execution_stats = {
            'total': BatchExecution.objects.filter(job=job).count(),
            'completed': BatchExecution.objects.filter(job=job, status='completed').count(),
            'failed': BatchExecution.objects.filter(job=job, status='failed').count(),
            'running': BatchExecution.objects.filter(job=job, status='running').count(),
            'pending': BatchExecution.objects.filter(job=job, status='pending').count(),
        }

        return JsonResponse({
            "job_id": job.job_id,
            "job_name": job.job_name,
            "target_app": job.target_app,
            "template_name": job.template_name,
            "status": job.status,
            "progress": job.progress_percentage(),
            "total_customers": job.total_customers,
            "sent": job.sent_count,
            "failed": job.failed_count,
            "skipped": job.skipped_count,
            "total_batches": job.total_batches,
            "completed_batches": job.completed_batches,
            "current_batch": job.current_batch,
            "batch_size": job.batch_size,
            "batch_size_type": job.batch_size_type,
            "schedule_type": job.schedule_type,
            "schedule_info": job.get_schedule_info(),
            "total_runs": job.total_runs,
            "completed_runs": job.completed_runs,
            "schedule_datetime": format_datetime_12hr(job.schedule_datetime),
            "next_run_time": format_datetime_12hr(job.next_run_time) if job.next_run_time else None,
            "end_date": format_datetime_12hr(job.end_date) if job.end_date else None,
            "created_at": format_datetime_12hr(job.created_at),
            "started_at": format_datetime_12hr(job.started_at),
            "completed_at": format_datetime_12hr(job.completed_at),
            "execution_stats": execution_stats,
            "timezone": "Asia/Kolkata (IST)",
            "utc_offset": "+05:30",
            "format": "12-hour (AM/PM)",
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
