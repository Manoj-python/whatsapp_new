# messaging/models.py
from django.db import models
from django.utils import timezone

class SmsWhatsAppLog(models.Model):
    job_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, default='')
    mobile = models.CharField(max_length=20, db_index=True)
    template_name = models.CharField(max_length=100, blank=True, default='')
    sent_text_message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, blank=True, default='', db_index=True)
    message_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    message_type = models.CharField(max_length=50, blank=True, default='', db_index=True)
    content_type = models.CharField(max_length=50, blank=True, default='text')
    media_file = models.FileField(upload_to='chat_media/', blank=True, null=True)
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    error_message = models.TextField(blank=True, default='')
    customer_name = models.CharField(max_length=255, blank=True, default='')  # Customer name (for received)
    # sender_name = models.CharField(max_length=255, blank=True, default='')  # Customer name (for received)


    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['mobile', '-sent_at']),
            models.Index(fields=['-sent_at']),
            models.Index(fields=['message_type', 'status']),
            models.Index(fields=['job_id']),
            models.Index(fields=['message_id']),
        ]
    
    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.sent_at}"

class ChatContact(models.Model):
    mobile = models.CharField(max_length=20, unique=True, db_index=True)
    last_msg = models.TextField(blank=True, default='')
    last_time = models.DateTimeField(default=timezone.now, db_index=True)
    last_type = models.CharField(max_length=20, blank=True, default='')
    # FIX: Increase max_length from 225 to 500
    last_status = models.CharField(max_length=500, blank=True, default='')  # Increased from 225
    unread = models.IntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Add these fields for assignment tracking
    assigned_to = models.CharField(max_length=100, blank=True, null=True)
    assigned_at = models.DateTimeField(blank=True, null=True)
    assigned_level = models.CharField(max_length=20, blank=True, null=True)
    current_level = models.CharField(max_length=20, default='ESC1', blank=True, null=True)
    
    class Meta:
        ordering = ['-last_time']
        indexes = [
            models.Index(fields=['-last_time', 'unread']),
            models.Index(fields=['mobile']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['current_level']),
        ]
    
    def to_dict(self):
        return {
            'mobile': self.mobile,
            'last_msg': self.last_msg or '',
            'last_type': self.last_type,
            'last_status': self.last_status,
            'unread': self.unread,
            'last_time': self.last_time.isoformat() if self.last_time else None,
            'assigned_to': self.assigned_to,
            'current_level': self.current_level or 'ESC1',
        }
    
    def __str__(self):
        return f"{self.mobile} - {self.last_msg[:30]}"


class BulkJob(models.Model):
    job_id = models.CharField(max_length=100, unique=True, db_index=True)
    template_name = models.CharField(max_length=100)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default='Pending', db_index=True)
    excel_file = models.CharField(max_length=500, blank=True, default='')
    success_report = models.FileField(upload_to="reports/", blank=True, null=True)
    failed_report = models.FileField(upload_to="reports/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    batch_size = models.IntegerField(default=50)
    completed_batches = models.IntegerField(default=0)
    priority = models.IntegerField(default=0)
    total_batches = models.IntegerField(default=0)

    
    
    class Meta:
        ordering = ['-created_at']


# ============================================
# CASE MANAGEMENT MODELS (shared with messaging2)
# ============================================

from messaging2.models import Agent  # reuse Agent from PSF app

class CaseEscalationLog(models.Model):
    case = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='escalation_logs')
    from_level = models.CharField(max_length=20)
    to_level = models.CharField(max_length=20)
    escalated_by = models.CharField(max_length=255, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: 
        ordering = ['-created_at']

class CaseAssignmentLog(models.Model):
    case = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='assignment_logs')
    assigned_to = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='sms_assignments')   # unique
    assigned_by = models.CharField(max_length=255, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: 
        ordering = ['-created_at']

class CaseComment(models.Model):
    case = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='comments')
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='sms_case_comments')   # unique
    agent_name = models.CharField(max_length=255, blank=True, null=True)
    comment = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: 
        ordering = ['created_at']


class Case(models.Model):
    """Case Management Model with Resolution Workflow"""
    
    ESCALATION_CHOICES = [
        ('ESC0', '🆕 New Case - Unassigned'),
        ('ESC1', '📞 Level 1 - Normal Agent'),
        ('ESC2', '⚖️ Level 2 - Legal Team'),
        ('ESC3', '⭐ Level 3 - Team Lead'),
        ('ESC4', '📊 Level 4 - Manager'),
        ('ESC5', '🔒 Level 5 - Admin'),
        ('RESOLVED', '✅ Resolved - Awaiting Closure'),
        ('CLOSED', '🔒 Closed - Final'),
    ]
    
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('On Hold', 'On Hold'),
        ('Resolved', 'Resolved - Pending Closure'),
        ('Closed', 'Closed - Final'),
        ('Reopened', 'Reopened'),
    ]
    
    PRIORITY_CHOICES = [
        ('Low', '🟢 Low'),
        ('Medium', '🟡 Medium'),
        ('High', '🟠 High'),
        ('Urgent', '🔴 Urgent'),
    ]
    
    # Basic Information
    case_id = models.CharField(max_length=50, unique=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    mobile = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True, null=True)
    loan_number = models.CharField(max_length=100, blank=True, null=True)
    vehicle_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Issue Details
    issue_description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    
    # Escalation
    current_level = models.CharField(max_length=20, choices=ESCALATION_CHOICES, default='ESC0')
    previous_level = models.CharField(max_length=20, blank=True, null=True)
    
    # Resolution Tracking
    resolved_at_level = models.CharField(max_length=20, blank=True, null=True)
    resolved_by_role = models.CharField(max_length=50, blank=True, null=True)
    
    # Status & Priority
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    
    # Assignment
    assigned_to = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='sms_assigned_cases')
    assigned_to_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    reopened_at = models.DateTimeField(blank=True, null=True)
    
    # Resolution & Closure
    resolution_notes = models.TextField(blank=True, null=True)
    resolved_by = models.CharField(max_length=255, blank=True, null=True)
    closed_by = models.CharField(max_length=255, blank=True, null=True)
    closed_reason = models.TextField(blank=True, null=True)
    
    # Reopen tracking
    reopen_count = models.IntegerField(default=0)
    reopen_reason = models.TextField(blank=True, null=True)
    
    # Metadata
    source = models.CharField(max_length=100, default='WhatsApp', blank=True, null=True)
    source_app = models.CharField(max_length=20, default='app1', choices=[
        ('app1', 'App 1 - messaging'),
        ('app2', 'App 2 - messaging2'),
        ('app3', 'App 3 - splcase'),
    ])
    created_by = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['case_id']),
            models.Index(fields=['mobile']),
            models.Index(fields=['current_level']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.case_id} - {self.current_level} - {self.status}"
    
    def escalate(self, new_level, agent, reason=None, loan=None, name=None):
        if self.status in ['Resolved', 'Closed']:
            raise ValueError(f"Cannot escalate a {self.status} case")
        if loan:
            self.loan_number = loan
        if name:
            self.customer_name = name
        self.previous_level = self.current_level
        self.current_level = new_level
        self.status = 'In Progress'
        self.updated_at = timezone.now()
        self.save()
        CaseEscalationLog.objects.create(
            case=self,
            from_level=self.previous_level,
            to_level=new_level,
            escalated_by=agent.name if agent else 'System',
            reason=reason or f"Escalated to {new_level}"
        )
        if agent:
            agent.increment_escalations()
        return True
    
    def resolve(self, agent, resolution_notes=None):
        if self.status == 'Closed':
            raise ValueError("Cannot resolve a closed case")
        self.resolved_at_level = self.current_level
        self.resolved_by_role = agent.role if agent else 'System'
        self.status = 'Resolved'
        self.current_level = 'RESOLVED'
        self.resolved_at = timezone.now()
        self.resolved_by = agent.name if agent else 'System'
        self.resolution_notes = resolution_notes
        self.updated_at = timezone.now()
        self.save()
        if agent:
            agent.increment_resolved_cases()
        CaseEscalationLog.objects.create(
            case=self,
            from_level=self.current_level,
            to_level='RESOLVED',
            escalated_by=agent.name if agent else 'System',
            reason=resolution_notes or 'Case resolved'
        )
        return True
    
    def close(self, agent, close_reason=None):
        if agent.role != 'ADMIN':
            raise PermissionError("Only Admin can close cases")
        if self.status != 'Resolved':
            raise ValueError(f"Cannot close case in {self.status} status")
        self.status = 'Closed'
        self.current_level = 'CLOSED'
        self.closed_at = timezone.now()
        self.closed_by = agent.name
        self.closed_reason = close_reason
        self.updated_at = timezone.now()
        self.save()
        CaseEscalationLog.objects.create(
            case=self,
            from_level='RESOLVED',
            to_level='CLOSED',
            escalated_by=agent.name,
            reason=close_reason or 'Case closed by admin'
        )
        return True
    
    def reopen(self, agent, reopen_reason=None, new_level=None):
        if self.status == 'Closed':
            if agent.role != 'ADMIN':
                raise PermissionError("Only Admin can reopen closed cases")
            target_level = new_level if new_level else (self.resolved_at_level or 'ESC1')
            self.reopen_count += 1
            self.reopen_reason = reopen_reason
            self.reopened_at = timezone.now()
            self.status = 'Reopened'
            self.current_level = target_level
            self.previous_level = 'CLOSED'
            self.closed_at = None
            self.closed_by = None
            self.closed_reason = None
            self.resolved_at = None
            self.resolved_by = None
            self.resolution_notes = None
            self.resolved_at_level = None
            self.resolved_by_role = None
            self.updated_at = timezone.now()
            self.save()
            CaseEscalationLog.objects.create(
                case=self,
                from_level='CLOSED',
                to_level=target_level,
                escalated_by=agent.name,
                reason=f"Reopened from closed: {reopen_reason or 'No reason provided'}"
            )
            return True
        if self.status == 'Resolved':
            target_level = new_level if new_level else (self.resolved_at_level or 'ESC1')
            self.reopen_count += 1
            self.reopen_reason = reopen_reason
            self.reopened_at = timezone.now()
            self.status = 'Reopened'
            self.current_level = target_level
            self.previous_level = 'RESOLVED'
            self.resolved_at = None
            self.resolved_by = None
            self.resolution_notes = None
            self.resolved_at_level = None
            self.resolved_by_role = None
            self.updated_at = timezone.now()
            self.save()
            CaseEscalationLog.objects.create(
                case=self,
                from_level='RESOLVED',
                to_level=target_level,
                escalated_by=agent.name,
                reason=f"Reopened: {reopen_reason or 'No reason provided'}"
            )
            return True
        raise ValueError(f"Cannot reopen case in {self.status} status. Only resolved or closed cases can be reopened.")
    
    def can_resolve(self, agent):
        return agent.is_active and self.status not in ['Resolved', 'Closed']
    
    def can_close(self, agent):
        return agent.role == 'ADMIN' and self.status == 'Resolved'
    
    def can_escalate(self, agent, target_level):
        if self.status in ['Resolved', 'Closed']:
            return False
        return agent.can_escalate_to(target_level)
    
    def assign_to_agent(self, agent, assigned_by=None, reason=None):
        self.assigned_to = agent
        self.assigned_to_name = agent.name
        self.save()
        CaseAssignmentLog.objects.create(
            case=self,
            assigned_to=agent,
            assigned_by=assigned_by,
            reason=reason
        )
        return True