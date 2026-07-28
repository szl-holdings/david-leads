# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Reads the locally stored David Leads credentials from Windows Credential Manager.

.DESCRIPTION
  Run only on the approved administrator workstation. Values are never stored in
  this repository or the operating manual. Do not paste the output into chat,
  email, tickets, screenshots, or logs. Transfer to David using an approved
  password manager's expiring secure-share feature.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class DavidCredentialReader {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct CREDENTIAL {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("Advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);

    [DllImport("Advapi32.dll", EntryPoint = "CredFree", SetLastError = true)]
    public static extern void CredFree(IntPtr credential);
}
"@

function Read-DavidCredential([string]$Target) {
    $pointer = [IntPtr]::Zero
    if (-not [DavidCredentialReader]::CredRead($Target, 1, 0, [ref]$pointer)) {
        throw "Credential target '$Target' is unavailable on this workstation."
    }
    try {
        $credential = [Runtime.InteropServices.Marshal]::PtrToStructure(
            $pointer,
            [type][DavidCredentialReader+CREDENTIAL]
        )
        $secret = [Runtime.InteropServices.Marshal]::PtrToStringUni(
            $credential.CredentialBlob,
            [int]($credential.CredentialBlobSize / 2)
        )
        [pscustomobject]@{
            Target = $Target
            UserName = $credential.UserName
            Secret = $secret
        }
    }
    finally {
        [DavidCredentialReader]::CredFree($pointer)
    }
}

Write-Warning "Sensitive output follows. Use only for an expiring password-manager handoff."
$login = Read-DavidCredential "SZL/david-leads/login"
$access = Read-DavidCredential "SZL/david-leads/access-key"
[pscustomobject]@{
    Username = $login.UserName
    Password = $login.Secret
    AccessKey = $access.Secret
} | Format-List
