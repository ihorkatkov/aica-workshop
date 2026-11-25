-- Seed the local workshop fixture in the schema shipped with LangWatch 3.23.0.
BEGIN;
SET LOCAL search_path TO mydb, public;
INSERT INTO "Organization" (id, name, slug)
VALUES ('aica_lab_org', 'AICA workshop', 'aica-lab') ON CONFLICT (id) DO NOTHING;
INSERT INTO "Team" (id, name, slug, "organizationId")
VALUES ('aica_lab_team', 'Workshop participants', 'aica-lab-team', 'aica_lab_org')
ON CONFLICT (id) DO NOTHING;
INSERT INTO "Project" (id, name, slug, "apiKey", "teamId", language, framework, integrated)
VALUES ('aica_lab_project', 'AICA workshop', 'aica-lab', 'lw-' || replace(gen_random_uuid()::text, '-', ''),
        'aica_lab_team', 'python', 'google-adk', true) ON CONFLICT (id) DO NOTHING;
INSERT INTO "OrganizationUser" ("userId", "organizationId", role)
VALUES ((SELECT id FROM "User" WHERE email = :'email'), 'aica_lab_org', 'ADMIN')
ON CONFLICT ("userId", "organizationId") DO NOTHING;
INSERT INTO "TeamUser" ("userId", "teamId", role)
VALUES ((SELECT id FROM "User" WHERE email = :'email'), 'aica_lab_team', 'ADMIN')
ON CONFLICT ("userId", "teamId") DO NOTHING;
-- The trace explorer checks scoped grants as well as organization membership.
INSERT INTO "Grant" (id, "organizationId", "principalType", "principalId", "roleKey",
                     source, "scopeType", "scopeId", "occurredAt")
VALUES ('aica_lab_dashboard_grant', 'aica_lab_org', 'USER',
        (SELECT id FROM "User" WHERE email = :'email'), 'admin', 'migration',
        'ORGANIZATION', 'aica_lab_org', CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;
UPDATE "User" SET "passkeyNudgeDismissedAt" = COALESCE("passkeyNudgeDismissedAt", CURRENT_TIMESTAMP),
                  "tracesExplorerTourDismissedAt" = COALESCE("tracesExplorerTourDismissedAt", CURRENT_TIMESTAMP)
WHERE email = :'email';
COMMIT;
SELECT "apiKey" FROM mydb."Project" WHERE id = 'aica_lab_project';
