# IMAP Email Provider Setup Guide

This system works with **any email provider that supports IMAP**. You only need to update the `.env` file with your provider's settings - no code changes required!

## Quick Setup

1. Find your provider's IMAP settings below
2. Update `.env` with the correct values
3. Create app-specific password if required
4. Configure folders in `config/config.yml`
5. Test with `python test_email.py`

## Supported Providers

### Gmail

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
```

**App Password Required:** Yes
- Go to https://myaccount.google.com/apppasswords
- Create a new app password
- Use that password (not your regular Gmail password)

**Folder Naming:**
- Uses labels as folders
- Nested labels use `"/"` separator: `"Receipts/Receipts (in Homebox)"`
- Top-level labels: Just the label name `"Receipts"`

**Notes:**
- Enable IMAP in Gmail settings: Settings → Forwarding and POP/IMAP → Enable IMAP
- Labels and folders are the same in Gmail

---

### Outlook / Office 365

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@outlook.com
EMAIL_PASSWORD=your-password
EMAIL_IMAP_HOST=outlook.office365.com
EMAIL_IMAP_PORT=993
```

**App Password Required:** Maybe
- If 2FA enabled, create app password at: https://account.microsoft.com/security
- Otherwise, use regular password

**Folder Naming:**
- Uses standard folders
- Nested folders use `"/"` separator: `"Receipts/Receipts (in Homebox)"`
- Inbox is `"INBOX"` (uppercase)

**Alternative Hosts:**
- Outlook.com: `imap-mail.outlook.com`
- Office 365: `outlook.office365.com`

---

### iCloud Mail

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@icloud.com
EMAIL_PASSWORD=app-specific-password
EMAIL_IMAP_HOST=imap.mail.me.com
EMAIL_IMAP_PORT=993
```

**App Password Required:** Yes
- Go to https://appleid.apple.com
- Sign in → Security → App-Specific Passwords
- Generate password for "Email to Homebox"

**Folder Naming:**
- Uses standard IMAP folders
- Nested folders use `"/"` separator
- Inbox is `"INBOX"`

**Notes:**
- Must have 2FA enabled on Apple ID
- App-specific passwords required (cannot use main password)

---

### Fastmail

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@fastmail.com
EMAIL_PASSWORD=your-password-or-app-password
EMAIL_IMAP_HOST=imap.fastmail.com
EMAIL_IMAP_PORT=993
```

**App Password Required:** Recommended
- Settings → Privacy & Security → App Passwords
- Create password for "Email to Homebox"

**Folder Naming:**
- Uses standard IMAP folders
- Nested folders use `"/"` separator
- Very flexible folder structure

**Notes:**
- Fastmail has excellent IMAP support
- Can use custom domains

---

### Yahoo Mail

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@yahoo.com
EMAIL_PASSWORD=app-password
EMAIL_IMAP_HOST=imap.mail.yahoo.com
EMAIL_IMAP_PORT=993
```

**App Password Required:** Yes
- Go to https://login.yahoo.com/account/security
- Generate app password
- Use that password (not your Yahoo password)

**Folder Naming:**
- Uses standard IMAP folders
- Nested folders use `"/"` separator
- Inbox is `"Inbox"` (capitalized)

---

### ProtonMail Bridge

**IMAP Settings:**
```bash
EMAIL_ADDRESS=your-email@proton.me
EMAIL_PASSWORD=bridge-password
EMAIL_IMAP_HOST=127.0.0.1
EMAIL_IMAP_PORT=1143
```

**App Password Required:** Bridge password
- Install ProtonMail Bridge desktop app
- Bridge generates a password for IMAP access
- Host is `localhost` or `127.0.0.1`

**Folder Naming:**
- Uses standard IMAP folders
- Nested folders use `"/"` separator

**Notes:**
- Requires ProtonMail Bridge (paid feature)
- Bridge must be running when processing emails

---

### Generic IMAP Server

For other providers, find these settings (usually in provider's help docs):

```bash
EMAIL_ADDRESS=your-email@provider.com
EMAIL_PASSWORD=your-password
EMAIL_IMAP_HOST=imap.provider.com  # e.g., mail.provider.com
EMAIL_IMAP_PORT=993  # Usually 993 for SSL
```

**Common IMAP ports:**
- 993: IMAP with SSL/TLS (most common, recommended)
- 143: IMAP without SSL (not recommended)

## Folder Configuration

After setting up your email provider, configure folders in `config/config.yml`:

```yaml
email:
  # Folders to monitor for receipts
  folders:
    - Receipts  # Or "INBOX/Receipts", "Inbox/Receipts", etc.

  # Where to move processed receipts (optional)
  move_to_folder_on_success: "Receipts/Receipts (in Homebox)"
  move_to_folder_on_low_confidence: "Receipts/Receipts (process manually)"
```

### Folder Naming Tips

**Most providers use `"/"` for nested folders:**
```yaml
folders:
  - "Receipts"  # Top-level folder
  - "INBOX/Receipts"  # Subfolder of INBOX
  - "Receipts/Amazon"  # Nested folder
```

**Some providers use `"."` instead:**
```yaml
folders:
  - "Receipts"
  - "INBOX.Receipts"
  - "Receipts.Amazon"
```

**Test your folder names:**
```bash
python test_email.py
```

If you see "No emails found", try different folder naming:
- `"Receipts"` vs `"INBOX/Receipts"`
- `"Receipts"` vs `"INBOX.Receipts"`
- `"INBOX"` vs `"Inbox"` (case-sensitive on some providers)

## Testing

### 1. Test Connection

```bash
python test_email.py
```

**Expected output:**
```
Connected to imap.gmail.com
Checking folder: Receipts
Found 5 email(s)
```

**If connection fails:**
- Check EMAIL_IMAP_HOST and EMAIL_IMAP_PORT
- Verify EMAIL_ADDRESS and EMAIL_PASSWORD
- Check if 2FA requires app password
- Enable IMAP in provider settings

### 2. Test Folder Access

If you see "No emails found" but you have emails:
- Check folder name in `config/config.yml`
- Try `"INBOX/Receipts"` instead of `"Receipts"`
- Try uppercase: `"INBOX"` instead of `"Inbox"`
- Check provider's folder structure (webmail interface)

### 3. Test Email Moving

The `move_to_folder` feature copies emails to another folder. Make sure destination folders exist:

**Gmail:**
1. Create labels: "Receipts/Receipts (in Homebox)"
2. Gmail automatically creates nested structure

**Outlook:**
1. Create folders in webmail or desktop client
2. Use `"Receipts/Receipts (in Homebox)"` syntax

**If moving fails:**
- Check destination folder exists
- Verify folder path syntax (try with/without `"INBOX/"` prefix)
- Some providers may not support moving between folders

## Troubleshooting

### "Failed to connect to email"

**Check:**
1. IMAP_HOST is correct
2. IMAP_PORT is correct (usually 993)
3. EMAIL_ADDRESS is correct
4. EMAIL_PASSWORD is correct (app password if required)
5. IMAP is enabled in provider settings

**Common fixes:**
- Use app password instead of regular password
- Enable IMAP in email settings
- Check firewall/network (IMAP uses port 993)

### "No emails found in Receipts folder"

**Check:**
1. Folder name in config matches actual folder name
2. Emails exist in that folder (check webmail)
3. Try different folder naming:
   ```yaml
   folders:
     - "Receipts"
     - "INBOX/Receipts"
     - "INBOX.Receipts"
   ```

### "Authentication failed" or "Invalid credentials"

**Gmail:**
- Use app password, not regular password
- Enable "Less secure app access" (not recommended) OR use app password

**Outlook:**
- If 2FA enabled, create app password
- Go to account.microsoft.com/security

**iCloud:**
- Must use app-specific password
- Regular password won't work

**Yahoo:**
- Must use app password
- Generate at login.yahoo.com/account/security

### "Failed to move email to folder"

**Check:**
1. Destination folder exists
2. Folder path is correct
3. Try with/without `"INBOX/"` prefix

**Workaround:**
Disable email moving temporarily:
```yaml
email:
  # Comment out or set to empty
  move_to_folder_on_success: ""
  move_to_folder_on_low_confidence: ""
```

## Provider-Specific Notes

### Gmail

**Pros:**
- Excellent IMAP support
- Labels work as folders
- Free for personal use

**Cons:**
- Requires app password (security)
- Label/folder structure can be confusing

**Tips:**
- Create nested labels like "Receipts/Receipts (in Homebox)"
- Labels appear as folders in IMAP

### Outlook/Office 365

**Pros:**
- Standard IMAP implementation
- Works with regular password (if 2FA disabled)
- Good folder support

**Cons:**
- May require app password with 2FA
- IMAP can be slow sometimes

**Tips:**
- Use `outlook.office365.com` for Office 365
- Use `imap-mail.outlook.com` for Outlook.com

### iCloud

**Pros:**
- Reliable IMAP
- Integrates with Apple ecosystem

**Cons:**
- Requires 2FA
- Must use app-specific password
- Free tier has storage limits

**Tips:**
- Generate app-specific password before setup
- Keep 2FA enabled (required)

### Fastmail

**Pros:**
- Excellent IMAP support (IMAP-focused provider)
- Fast and reliable
- Flexible folder management

**Cons:**
- Paid service only
- Less common than Gmail/Outlook

**Tips:**
- Create app passwords for security
- Great for custom domains

## Security Best Practices

1. **Always use app-specific passwords when available**
   - Don't use your main email password
   - Limits access if credentials leaked

2. **Use SSL/TLS (port 993)**
   - Never use port 143 without SSL
   - Ensures encrypted connection

3. **Store `.env` securely**
   - Don't commit to git
   - Set file permissions: `chmod 600 .env`

4. **Rotate passwords periodically**
   - Regenerate app passwords every 6-12 months
   - Revoke unused app passwords

5. **Enable 2FA on email account**
   - Adds extra security layer
   - Requires app passwords (which is good!)

## Quick Reference

| Provider | IMAP Host | Port | App Password | Folder Separator |
|----------|-----------|------|--------------|------------------|
| Gmail | imap.gmail.com | 993 | Required | `/` |
| Outlook | outlook.office365.com | 993 | If 2FA | `/` |
| iCloud | imap.mail.me.com | 993 | Required | `/` |
| Fastmail | imap.fastmail.com | 993 | Recommended | `/` |
| Yahoo | imap.mail.yahoo.com | 993 | Required | `/` |
| ProtonMail | 127.0.0.1 | 1143 | Bridge | `/` |

## Still Having Issues?

1. **Check provider's help docs** for IMAP settings
2. **Test with an email client** (Thunderbird, Apple Mail) to verify IMAP works
3. **Enable debug logging:**
   ```bash
   # Edit config/config.yml or set in .env
   LOG_LEVEL=DEBUG
   python test_email.py
   ```
4. **Check firewall/network** - Port 993 must be open
5. **Try a different provider** - Gmail and Fastmail have the best IMAP support

## Summary

The system works with **any IMAP provider** - just update these settings in `.env`:
- `EMAIL_ADDRESS` - Your email address
- `EMAIL_PASSWORD` - Your password (or app password)
- `EMAIL_IMAP_HOST` - Provider's IMAP server
- `EMAIL_IMAP_PORT` - Usually 993

No code changes needed! 🎉
