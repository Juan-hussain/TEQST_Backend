from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from textmgmt.models import SharedFolder, RecentProject

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix RecentProject entries to only include folders where users have speaker permissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Fix RecentProject entries for a specific user (optional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        dry_run = options.get('dry_run', False)
        
        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User "{username}" not found')
                )
                return
        else:
            users = User.objects.all()

        total_fixed = 0
        
        for user in users:
            self.stdout.write(f'Processing user: {user.username}')
            
            # Get all RecentProject entries for this user
            recent_projects = RecentProject.objects.filter(speaker=user)
            invalid_entries = []
            valid_entries = []
            
            for rp in recent_projects:
                try:
                    # Check if it's a SharedFolder and if user has permissions
                    shared_folder = SharedFolder.objects.get(id=rp.folder.id)
                    if shared_folder.is_speaker(user) or shared_folder.public:
                        valid_entries.append(rp)
                    else:
                        # Check if it's a DEFAULT_FOLDER - these should always be valid
                        from django.conf import settings
                        if hasattr(settings, 'DEFAULT_FOLDER') and settings.DEFAULT_FOLDER:
                            folder_uuids = [str(f.root_id) for f in [rp.folder]]
                            if any(str(uuid) in [str(f_uuid) for f_uuid in settings.DEFAULT_FOLDER] for uuid in folder_uuids):
                                valid_entries.append(rp)
                            else:
                                invalid_entries.append(rp)
                        else:
                            invalid_entries.append(rp)
                except SharedFolder.DoesNotExist:
                    # Not a SharedFolder, but check if it's a DEFAULT_FOLDER
                    from django.conf import settings
                    if hasattr(settings, 'DEFAULT_FOLDER') and settings.DEFAULT_FOLDER:
                        folder_uuids = [str(f.root_id) for f in [rp.folder]]
                        if any(str(uuid) in [str(f_uuid) for f_uuid in settings.DEFAULT_FOLDER] for uuid in folder_uuids):
                            valid_entries.append(rp)
                        else:
                            invalid_entries.append(rp)
                    else:
                        invalid_entries.append(rp)
            
            if invalid_entries:
                self.stdout.write(
                    f'  Found {len(invalid_entries)} invalid RecentProject entries:'
                )
                for rp in invalid_entries:
                    self.stdout.write(f'    - {rp.folder.name} (ID: {rp.folder.id})')
                
                if not dry_run:
                    # Remove invalid entries
                    for rp in invalid_entries:
                        rp.delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'  Removed {len(invalid_entries)} invalid entries')
                    )
                    total_fixed += len(invalid_entries)
                else:
                    self.stdout.write('  [DRY RUN] Would remove these entries')
            
            if valid_entries:
                self.stdout.write(f'  Found {len(valid_entries)} valid RecentProject entries')
                for rp in valid_entries:
                    self.stdout.write(f'    - {rp.folder.name} (ID: {rp.folder.id})')
            
            # Check for SharedFolders where user has permissions but no RecentProject entry
            shared_folders = SharedFolder.objects.filter(speaker=user)
            missing_entries = []
            
            for sf in shared_folders:
                if not RecentProject.objects.filter(speaker=user, folder=sf).exists():
                    missing_entries.append(sf)
            
            # Also check for DEFAULT_FOLDERs that might be missing
            from django.conf import settings
            if hasattr(settings, 'DEFAULT_FOLDER') and settings.DEFAULT_FOLDER:
                from textmgmt.models import Folder
                for f_uuid in settings.DEFAULT_FOLDER:
                    try:
                        folder = Folder.objects.get(root_id=f_uuid)
                        if not RecentProject.objects.filter(speaker=user, folder=folder).exists():
                            missing_entries.append(folder)
                    except Folder.DoesNotExist:
                        pass
            
            if missing_entries:
                self.stdout.write(
                    f'  Found {len(missing_entries)} folders with permissions but no RecentProject entry:'
                )
                for sf in missing_entries:
                    self.stdout.write(f'    - {sf.name} (ID: {sf.id})')
                
                if not dry_run:
                    # Add missing entries
                    for sf in missing_entries:
                        RecentProject.update_folder_for_speaker(user, sf)
                    self.stdout.write(
                        self.style.SUCCESS(f'  Added {len(missing_entries)} missing entries')
                    )
                    total_fixed += len(missing_entries)
                else:
                    self.stdout.write('  [DRY RUN] Would add these entries')
            
            if not invalid_entries and not missing_entries:
                self.stdout.write('  No changes needed')
            
            self.stdout.write('')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETE - No changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'COMPLETE - Fixed {total_fixed} RecentProject entries')
            )
