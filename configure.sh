#!/bin/bash
set -e
echo "🔧 Configuring Research Desk..."
cp frontend/index.html frontend/index.html.backup
sed -i '' "s|const SUPABASE_URL = 'YOUR_SUPABASE_URL';|const SUPABASE_URL = 'https://aleirqepbkelpujixrb.supabase.co';|g" frontend/index.html
sed -i '' "s|const SUPABASE_ANON_KEY = 'YOUR_SUPABASE_ANON_KEY';|const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFsZWlycWVwYnBrZWxwdWppeHJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ4ODY1NjUsImV4cCI6MjExMDQ2MjU2NX0.XZVVIvRo7CeZhnzTSXgPLfV28GBVrI1B5jwByEym6Zg';|g" frontend/index.html
echo "✅ Done!"
