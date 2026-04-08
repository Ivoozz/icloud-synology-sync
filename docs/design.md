# Design Spec: iCloud to Synology Photos Direct Streamer

**Date:** 2026-04-08
**Status:** Draft (Pending User Review)
**Target Platform:** Windows (.exe)

## 1. Objective
Create a standalone Windows application that performs two-way synchronization between Apple iCloud Photos and a Synology NAS (specifically Synology Photos), without consuming local disk space on the host PC during the transfer process.

## 2. Core Requirements
- **Memory-Only Streaming:** Photos and videos must be streamed from iCloud to Synology via system RAM. No temporary files should be written to the local disk.
- **Two-Way Synchronization:**
    - New iCloud items -> Upload to Synology.
    - Deleted iCloud items -> Delete from Synology.
    - Deleted Synology items -> Delete from iCloud (Optional/Configurable).
- **Direct NAS Connection:** Communicate with Synology DSM/Photos API directly via IP address (no mapped network drives required).
- **Authentication:** 
    - Support for Apple ID + App-Specific Passwords.
    - Support for Synology user credentials.
- **Resilience:** Handle NAS offline states gracefully without data loss or "false positive" deletions.
- **Local Persistence:** Maintain a small SQLite database to track sync states and IDs.

## 3. Architecture & Components

### 3.1. The Sync Engine (Python)
The core logic will be implemented in Python and packaged as an `.exe` using PyInstaller.
- **iCloud Interface:** Uses `pyicloud` to interact with the iCloud Photo Library.
- **Synology Interface:** Uses the Synology Photos API (DSM 7+) to upload, list, and delete media.
- **Streaming Buffer:** Uses `requests` or `aiohttp` to pipe the data stream from the iCloud GET request directly into the Synology POST request.

### 3.2. Metadata Store (SQLite)
A local `sync_state.db` file will store:
- `icloud_id`: The unique identifier from Apple.
- `synology_id`: The unique file identifier/path from Synology.
- `file_hash`: To detect content changes.
- `last_seen`: Timestamp of last successful sync.

### 3.3. Configuration Management
A `config.json` file will store non-sensitive configuration:
- `nas_ip`, `nas_user`.
- `apple_id`.
- `sync_interval_minutes`.
- `enable_nas_to_icloud_deletion`: Boolean toggle.

Sensitive credentials will be securely stored in the system's credentials vault (e.g., Windows Credential Manager) via the `keyring` library:
- `nas_password`.
- `app_specific_password`.

## 4. Operational Logic

### 4.1. The Sync Cycle
1. **Connectivity Check:** Ping NAS IP and verify API login. If fail, enter "Safe Pause" mode.
2. **iCloud Scan:** Fetch list of current photo IDs from iCloud.
3. **NAS Scan:** Fetch list of current photo IDs/Paths from the Synology Photos directory.
4. **Reconciliation:**
    - **Additions:** Items in iCloud but not in SQLite -> Stream to NAS.
    - **iCloud Deletions:** Items in SQLite but not in iCloud -> Delete from NAS.
    - **NAS Deletions:** Items in SQLite but not on NAS -> If `enable_nas_to_icloud_deletion` is TRUE, delete from iCloud; else, remove from SQLite only.

### 4.2. Safe Pause Mechanism
To prevent accidental deletions when the NAS is offline, the "Delete from iCloud" logic is strictly gated by a successful "Heartbeat" check to the NAS at the start of the cycle.

## 5. Security
- Use Windows Data Protection API (DPAPI) via the `keyring` library to encrypt credentials stored in the local config.
- Passwords are never logged or displayed in plain text.

## 6. Automated Testing Strategy

To ensure reliability and prevent data loss, the project will follow a strict testing protocol.

### 6.1. Unit Testing (Pytest)
- **Sync Logic:** Mock both iCloud and Synology API responses to verify the "Reconciliation" logic (Scenario A, B, and C).
- **Configuration:** Test encryption/decryption of settings using mock DPAPI keys.
- **Database:** Verify SQLite operations (insert, delete, query) for sync states.

### 6.2. Integration Testing
- **Streaming Buffer:** Use a local mock HTTP server (e.g., `FastAPI` or `http.server`) to simulate streaming 1GB of data and verify that the memory usage of the Python process remains constant and low.
- **NAS Offline Scenarios:** Simulate network timeouts and 404/503 errors from the "NAS" to verify the "Safe Pause" logic.

### 6.3. Manual Validation (Staging)
- Use a "Test Album" in iCloud and a "Test Folder" on the Synology for initial validation before allowing the app access to the full library.

## 7. Implementation Phases (High-Level)
1. **Phase 1:** CLI Bridge (iCloud -> NAS one-way stream) + Unit Tests for Streaming.
2. **Phase 2:** Metadata Database & Two-way logic + Sync Logic Tests.
3. **Phase 3:** Windows UI & Config Management + Integration Tests.
4. **Phase 4:** Packaging as .exe & Final Validation.
