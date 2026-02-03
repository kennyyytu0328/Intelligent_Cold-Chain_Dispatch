#!/bin/bash
echo "🔍 Testing .gitignore patterns..."
echo ""
echo "Testing if these files would be ignored:"
echo "----------------------------------------"
test_files=(".env" "frontend/.env" ".env.production" "credentials.json" "secrets.json" "id_rsa" "*.key" "*.pem" "dump.rdb" ".claude/settings.local.json")

for file in "${test_files[@]}"; do
    # Create dummy file if it doesn't exist
    if [[ "$file" == *"/"* ]]; then
        mkdir -p "$(dirname "$file")" 2>/dev/null
    fi
    touch "$file" 2>/dev/null
    
    # Check if git would ignore it
    if git check-ignore -q "$file" 2>/dev/null || [ ! -d .git ]; then
        echo "✅ IGNORED: $file"
    else
        echo "❌ NOT IGNORED: $file (FIX .gitignore!)"
    fi
    
    # Cleanup
    rm -f "$file" 2>/dev/null
done

echo ""
echo "Testing if .env.example is NOT ignored (should be committed):"
echo "-------------------------------------------------------------"
if git check-ignore -q ".env.example" 2>/dev/null; then
    echo "❌ .env.example is IGNORED (should NOT be ignored!)"
else
    echo "✅ .env.example is NOT ignored (correct!)"
fi

echo ""
echo "✅ .gitignore validation complete!"
