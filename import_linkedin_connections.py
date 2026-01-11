"""
LinkedIn Connections Import & Matching Script

This script:
1. Imports LinkedIn connections from CSV export
2. Matches connections to existing contacts (by name)
3. Updates contacts with LinkedIn URLs where matched
4. Reports unmatched connections for manual review

Usage:
    python import_linkedin_connections.py [--csv-path PATH] [--dry-run]
"""

import os
import csv
import re
import argparse
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from collections import defaultdict

from supabase import create_client


# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojnllduebzfxqmiyinhx.supabase.co").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()


def normalize_name(name: str) -> str:
    """Normalize name for matching: lowercase, remove special chars, trim."""
    if not name:
        return ""
    # Remove emojis and special characters, keep only letters, spaces, hyphens
    name = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE)
    # Normalize whitespace and lowercase
    return ' '.join(name.lower().split())


def parse_date(date_str: str) -> Optional[str]:
    """Parse LinkedIn date format (e.g., '11-Jan-26') to ISO date."""
    if not date_str:
        return None
    try:
        # LinkedIn uses DD-Mon-YY format
        dt = datetime.strptime(date_str.strip(), "%d-%b-%y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def load_csv(csv_path: str) -> List[Dict]:
    """Load LinkedIn connections from CSV."""
    connections = []
    
    # Try different encodings
    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                # Skip the first 3 rows (notes/empty lines)
                for _ in range(3):
                    next(f, None)
                
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('URL') and row.get('First Name'):
                        connections.append({
                            'first_name': row.get('First Name', '').strip(),
                            'last_name': row.get('Last Name', '').strip(),
                            'linkedin_url': row.get('URL', '').strip(),
                            'email': row.get('Email Address', '').strip() or None,
                            'company': row.get('Company', '').strip() or None,
                            'position': row.get('Position', '').strip() or None,
                            'connected_on': parse_date(row.get('Connected On', '')),
                        })
            print(f"  Loaded with encoding: {encoding}")
            break
        except UnicodeDecodeError:
            continue
    
    return connections


def match_contact(
    supabase,
    first_name: str,
    last_name: str,
    email: Optional[str] = None
) -> Tuple[Optional[str], str, str]:
    """
    Try to match a LinkedIn connection to an existing contact.
    
    Returns: (contact_id, confidence, notes)
    - confidence: 'exact', 'fuzzy', 'email', 'unmatched'
    """
    
    # Normalize names for comparison
    norm_first = normalize_name(first_name)
    norm_last = normalize_name(last_name)
    full_name = f"{norm_first} {norm_last}".strip()
    
    # Strategy 1: Exact match on email (if available)
    if email:
        result = supabase.table("contacts").select("id, first_name, last_name").eq("email", email.lower()).execute()
        if result.data:
            contact = result.data[0]
            return contact['id'], 'email', f"Email match: {email}"
    
    # Strategy 2: Exact name match (case-insensitive)
    result = supabase.table("contacts").select("id, first_name, last_name, linkedin_url").execute()
    contacts = result.data or []
    
    exact_matches = []
    fuzzy_matches = []
    
    for contact in contacts:
        c_first = normalize_name(contact.get('first_name', ''))
        c_last = normalize_name(contact.get('last_name', ''))
        c_full = f"{c_first} {c_last}".strip()
        
        # Exact match
        if c_first == norm_first and c_last == norm_last:
            exact_matches.append(contact)
        # Partial matches
        elif c_first == norm_first and norm_last.startswith(c_last[:3]) if c_last else False:
            fuzzy_matches.append((contact, 'last_name_partial'))
        elif c_last == norm_last and norm_first.startswith(c_first[:3]) if c_first else False:
            fuzzy_matches.append((contact, 'first_name_partial'))
        # First name only match (for single-name contacts)
        elif not c_last and c_first == norm_first:
            fuzzy_matches.append((contact, 'first_name_only'))
        # Full name in one field
        elif full_name == c_first or full_name == c_last:
            fuzzy_matches.append((contact, 'full_name_in_field'))
    
    # Return exact match if unique
    if len(exact_matches) == 1:
        contact = exact_matches[0]
        return contact['id'], 'exact', f"Exact match: {contact.get('first_name')} {contact.get('last_name')}"
    elif len(exact_matches) > 1:
        # Multiple exact matches - need manual review
        names = [f"{c.get('first_name')} {c.get('last_name')}" for c in exact_matches]
        return None, 'multiple', f"Multiple exact matches found: {', '.join(names)}"
    
    # Return fuzzy match if unique
    if len(fuzzy_matches) == 1:
        contact, match_type = fuzzy_matches[0]
        return contact['id'], 'fuzzy', f"Fuzzy match ({match_type}): {contact.get('first_name')} {contact.get('last_name')}"
    elif len(fuzzy_matches) > 1:
        names = [f"{c.get('first_name')} {c.get('last_name')}" for c, _ in fuzzy_matches]
        return None, 'multiple_fuzzy', f"Multiple fuzzy matches: {', '.join(names)}"
    
    return None, 'unmatched', "No matching contact found"


def main():
    parser = argparse.ArgumentParser(description='Import LinkedIn connections')
    parser.add_argument('--csv-path', default=r'C:\Projects\Connections Linkedin.csv',
                        help='Path to LinkedIn connections CSV')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report matches, do not modify database')
    parser.add_argument('--update-contacts', action='store_true',
                        help='Update contacts table with LinkedIn URLs')
    args = parser.parse_args()
    
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY environment variable not set")
        print("Set it with: $env:SUPABASE_KEY='your-key'")
        return
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Load CSV
    print(f"Loading connections from: {args.csv_path}")
    connections = load_csv(args.csv_path)
    print(f"Found {len(connections)} connections")
    
    # Match statistics
    stats = defaultdict(int)
    unmatched = []
    matched = []
    
    print("\nMatching connections to contacts...")
    
    for conn in connections:
        contact_id, confidence, notes = match_contact(
            supabase,
            conn['first_name'],
            conn['last_name'],
            conn['email']
        )
        
        conn['matched_contact_id'] = contact_id
        conn['match_confidence'] = confidence
        conn['match_notes'] = notes
        
        stats[confidence] += 1
        
        if contact_id:
            matched.append(conn)
        else:
            unmatched.append(conn)
    
    # Print statistics
    print("\n" + "="*60)
    print("MATCHING RESULTS")
    print("="*60)
    print(f"  Total connections: {len(connections)}")
    print(f"  ✅ Matched (exact): {stats['exact']}")
    print(f"  ✅ Matched (email): {stats['email']}")
    print(f"  🔶 Matched (fuzzy): {stats['fuzzy']}")
    print(f"  ❌ Unmatched: {stats['unmatched']}")
    print(f"  ⚠️  Multiple matches: {stats['multiple'] + stats['multiple_fuzzy']}")
    
    # Show unmatched for manual review
    print("\n" + "="*60)
    print("UNMATCHED CONNECTIONS (Manual Review Needed)")
    print("="*60)
    for conn in unmatched[:50]:  # Show first 50
        name = f"{conn['first_name']} {conn['last_name']}"
        company = conn['company'] or 'N/A'
        print(f"  - {name:<30} | {company[:25]:<25} | {conn['linkedin_url']}")
    
    if len(unmatched) > 50:
        print(f"  ... and {len(unmatched) - 50} more unmatched connections")
    
    if args.dry_run:
        print("\n[DRY RUN] No changes made to database")
        return
    
    # Insert into linkedin_connections table
    print("\n" + "="*60)
    print("INSERTING INTO linkedin_connections TABLE")
    print("="*60)
    
    inserted = 0
    skipped = 0
    
    for conn in connections:
        try:
            # Check if already exists
            existing = supabase.table("linkedin_connections").select("id").eq("linkedin_url", conn['linkedin_url']).execute()
            if existing.data:
                skipped += 1
                continue
            
            # Insert
            supabase.table("linkedin_connections").insert({
                'first_name': conn['first_name'],
                'last_name': conn['last_name'],
                'linkedin_url': conn['linkedin_url'],
                'email': conn['email'],
                'company': conn['company'],
                'position': conn['position'],
                'connected_on': conn['connected_on'],
                'matched_contact_id': conn['matched_contact_id'],
                'match_confidence': conn['match_confidence'],
                'match_notes': conn['match_notes'],
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"  Error inserting {conn['first_name']} {conn['last_name']}: {e}")
    
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (already exists): {skipped}")
    
    # Update contacts with LinkedIn URLs
    if args.update_contacts and matched:
        print("\n" + "="*60)
        print("UPDATING CONTACTS WITH LINKEDIN URLS")
        print("="*60)
        
        updated = 0
        already_has_url = 0
        
        for conn in matched:
            if not conn['matched_contact_id']:
                continue
            
            try:
                # Check if contact already has a LinkedIn URL
                contact = supabase.table("contacts").select("id, linkedin_url").eq("id", conn['matched_contact_id']).execute()
                if contact.data and contact.data[0].get('linkedin_url'):
                    already_has_url += 1
                    continue
                
                # Update contact
                supabase.table("contacts").update({
                    'linkedin_url': conn['linkedin_url'],
                    'updated_at': datetime.utcnow().isoformat()
                }).eq("id", conn['matched_contact_id']).execute()
                updated += 1
                
            except Exception as e:
                print(f"  Error updating contact for {conn['first_name']}: {e}")
        
        print(f"  Updated: {updated}")
        print(f"  Already had URL: {already_has_url}")
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
