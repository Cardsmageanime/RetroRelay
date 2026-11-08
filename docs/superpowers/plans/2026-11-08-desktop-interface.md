# RetroRelay desktop interface implementation

Implement the owner-approved navy/teal lobby-browser design in the existing Tkinter app.
Keep server APIs, emulator setup, hosting, matching and waiting-room operations intact.

1. Add sidebar navigation and a persistent account/connection header, retaining existing page switching.
2. Add searchable platform/method-filtered lobby discovery, selected-room details, file/folder selection and the existing verified join flow. Clear stale room details when results change.
3. Add a clearly marked planned achievements page; document existing security behavior accurately.
4. Test filtering and selection with real Tk widgets, navigation, authentication transitions, existing API tests, and inspect rendered desktop screenshots before publishing.

Use existing Python/Tkinter dependencies. Do not bundle game artwork or fake live lobbies. Use real room data and honest empty/offline states. Achievements provider integrations are outside this layout change.
