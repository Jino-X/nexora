-- Voice sessions start hands-free by default. push_to_talk_enabled is the "Hold to talk" setting; with it on, new
-- users opened a session with the microphone off and no greeting until they held the button.
-- Existing rows keep their current choice (changeable in Settings → Voice conversations).
alter table public.user_preferences alter column push_to_talk_enabled set default false;
