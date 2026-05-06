# messaging/management/commands/sync_contacts.py

import re
from django.core.management.base import BaseCommand
from django.db.models import Max, Count, Q
from django.utils import timezone
from messaging.models import SmsWhatsAppLog, ChatContact
from messaging.utils import format_mobile

class Command(BaseCommand):
    help = 'Sync existing messages to ChatContact table'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting contact sync...'))
        
        # Get all unique mobiles
        mobiles = SmsWhatsAppLog.objects.filter(
            mobile__isnull=False
        ).exclude(
            mobile=''
        ).values_list('mobile', flat=True).distinct()
        
        created = 0
        updated = 0
        
        for mobile in mobiles:
            formatted_mobile = format_mobile(mobile)
            
            # Get latest message
            latest = SmsWhatsAppLog.objects.filter(
                mobile=mobile
            ).order_by('-sent_at').first()
            
            # Count unread messages
            unread = SmsWhatsAppLog.objects.filter(
                mobile=mobile,
                message_type='Received',
                status='Unread'
            ).count()
            
            if latest:
                # Determine last status
                if latest.message_type == 'Received':
                    last_status = 'Read'
                else:
                    last_status = latest.status if latest.status else 'Sent'
                
                contact, is_created = ChatContact.objects.update_or_create(
                    mobile=formatted_mobile,
                    defaults={
                        'last_msg': latest.sent_text_message[:500] if latest.sent_text_message else '',
                        'last_time': latest.sent_at,
                        'last_type': latest.message_type,
                        'last_status': last_status,
                        'unread': unread,
                    }
                )
                
                if is_created:
                    created += 1
                    self.stdout.write(f'✅ Created: {formatted_mobile}')
                else:
                    updated += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Sync Complete! Created: {created}, Updated: {updated}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'📊 Total Contacts: {ChatContact.objects.count()}'
        ))