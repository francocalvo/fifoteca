# Manual Match Management Feature - Implementation Plan

## Overview
This feature adds the ability to manually create, edit, and delete matches from the analytics tab with an opponent approval workflow.

## User Decisions
- **Edits/Deletes:** Require opponent approval
- **Visual distinction:** No distinction for manual matches (they look like regular matches)
- **Request expiry:** 24 hours
- **Notifications:** Both popup dialog + persistent section

---

## Backend Changes

### New Model (`backend/app/models.py`)
- Added `ManualMatchRequestType` enum: `create`, `edit`, `delete`
- Added `ManualMatchRequestStatus` enum: `pending`, `accepted`, `declined`, `expired`, `cancelled`
- Added `FifotecaManualMatchRequest` table for storing pending requests
- Added public schemas: `ManualMatchCreateRequest`, `ManualMatchEditRequest`, `ManualMatchDeleteRequest`, `ManualMatchRequestPublic`, `ManualMatchRequestsPublic`

### New API Endpoints (`backend/app/api/routes/fifoteca/manual_matches.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/manual-matches/create` | POST | Create a manual match request |
| `/manual-matches/edit` | POST | Create an edit score request |
| `/manual-matches/delete` | POST | Create a delete match request |
| `/manual-matches` | GET | List pending requests (incoming + outgoing) |
| `/manual-matches/{id}/accept` | POST | Accept a request |
| `/manual-matches/{id}/decline` | POST | Decline a request |
| `/manual-matches/{id}` | DELETE | Cancel own pending request |

### WebSocket Notifications
The backend sends these message types via global WebSocket:
- `manual_match_request_received` - Sent to responder when a new request is created
- `manual_match_request_accepted` - Sent to requester when their request is accepted
- `manual_match_request_declined` - Sent to requester when their request is declined

### Database Migration
- File: `backend/app/alembic/versions/b2c3d4e5f6g7_add_manual_match_request_table.py`
- Creates the `fifotecamanualmatchrequest` table

---

## Frontend Changes

### New Components

#### 1. ManualMatchDialog (`frontend/src/components/fifoteca/ManualMatchDialog.tsx`)
Form for creating manual matches:
- League selector dropdown
- Team selector for requester (filtered by league)
- Team selector for responder (filtered by league)
- Auto-calculated rating difference display
- Score inputs for both players
- Submit creates pending request

#### 2. ManualMatchRequestDialog (`frontend/src/components/fifoteca/ManualMatchRequestDialog.tsx`)
Popup for incoming requests (similar to InviteReceivedDialog):
- Shows request details (type, teams, scores)
- Accept/Decline buttons
- Shows time remaining until expiry
- Listens to `lastGlobalMessage` from WebSocket context

#### 3. EditMatchDialog (`frontend/src/components/fifoteca/EditMatchDialog.tsx`)
Form for editing match scores:
- Shows current match info and scores
- Input fields for new scores
- Submit creates edit request

#### 4. PendingRequestsCard (`frontend/src/components/fifoteca/PendingRequestsCard.tsx`)
Persistent section showing all pending requests:
- **Incoming requests**: Shows accept/decline buttons
- **Outgoing requests**: Shows cancel button
- Auto-refreshes every minute for time remaining updates

### Updated Components

#### AnalyticsMatchHistory (`frontend/src/components/fifoteca/AnalyticsMatchHistory.tsx`)
- Added "Edit" toggle button in header
- When edit mode is active, shows edit (pencil) and delete (trash) buttons per row
- Edit button opens EditMatchDialog
- Delete button creates delete request directly

#### Analytics Page (`frontend/src/routes/_layout/fifoteca/analytics.tsx`)
- Added "Add Match" button (visible when opponent is selected)
- Added PendingRequestsCard section at the top
- Integrated ManualMatchDialog

#### Layout (`frontend/src/routes/_layout.tsx`)
- Added ManualMatchRequestDialog for global real-time popups

### API Client Updates (`frontend/src/client/`)
- Added types in `types.gen.ts`
- Added service methods in `sdk.gen.ts`

---

## How It Works

### Adding a Manual Match
1. Go to Analytics tab
2. Select an opponent
3. Click "Add Match" button
4. Select a league
5. Select teams for both players (rating difference auto-calculated)
6. Enter the final score
7. Click "Send Request"
8. Opponent receives a popup notification
9. Opponent can accept or decline
10. If accepted, match is created and stats are updated

### Editing a Match
1. Go to Analytics tab
2. Select the opponent for the match you want to edit
3. Click "Edit" button to enter edit mode
4. Click the pencil icon on the match row
5. Enter new scores
6. Click "Send Edit Request"
7. Opponent receives notification
8. If accepted, scores are updated and stats are recalculated

### Deleting a Match
1. Go to Analytics tab
2. Select the opponent for the match you want to delete
3. Click "Edit" button to enter edit mode
4. Click the trash icon on the match row
5. Delete request is sent immediately
6. Opponent receives notification
7. If accepted, match is deleted and stats are reversed

---

## Testing Checklist

### Prerequisites
- [ ] Run database migration: `alembic upgrade head`
- [ ] Start backend server
- [ ] Start frontend dev server
- [ ] Have two user accounts logged in (different browsers/incognito)

### Manual Match Creation
- [ ] Select opponent in Analytics tab
- [ ] Click "Add Match" button
- [ ] Select league, teams, enter scores
- [ ] Verify rating difference is calculated
- [ ] Submit request
- [ ] Verify opponent receives popup notification
- [ ] Accept request as opponent
- [ ] Verify match appears in history
- [ ] Verify player stats are updated

### Edit Match
- [ ] Enter edit mode in Analytics
- [ ] Click edit on a match
- [ ] Change scores
- [ ] Submit edit request
- [ ] Accept as opponent
- [ ] Verify scores are updated
- [ ] Verify stats are recalculated

### Delete Match
- [ ] Enter edit mode in Analytics
- [ ] Click delete on a match
- [ ] Accept as opponent
- [ ] Verify match is removed
- [ ] Verify stats are reversed

### Decline/Cancel
- [ ] Decline an incoming request
- [ ] Verify requester is notified
- [ ] Cancel an outgoing request
- [ ] Verify it's removed from pending

### Expiry
- [ ] Create a request
- [ ] Wait for expiry (or modify expiry time for testing)
- [ ] Verify request is no longer available

---

## File Changes Summary

### New Files
- `backend/app/api/routes/fifoteca/manual_matches.py`
- `backend/app/alembic/versions/b2c3d4e5f6g7_add_manual_match_request_table.py`
- `frontend/src/components/fifoteca/ManualMatchDialog.tsx`
- `frontend/src/components/fifoteca/ManualMatchRequestDialog.tsx`
- `frontend/src/components/fifoteca/EditMatchDialog.tsx`
- `frontend/src/components/fifoteca/PendingRequestsCard.tsx`

### Modified Files
- `backend/app/models.py` - Added enums and model
- `backend/app/api/routes/fifoteca/__init__.py` - Registered new router
- `frontend/src/client/types.gen.ts` - Added types
- `frontend/src/client/sdk.gen.ts` - Added service methods
- `frontend/src/components/fifoteca/index.ts` - Exported new components
- `frontend/src/components/fifoteca/AnalyticsMatchHistory.tsx` - Added edit mode
- `frontend/src/routes/_layout/fifoteca/analytics.tsx` - Integrated features
- `frontend/src/routes/_layout.tsx` - Added ManualMatchRequestDialog
