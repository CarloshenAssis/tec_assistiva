-- Hardening de segurança para um projeto Supabase desta aplicação.
--
-- Motivo (detalhado no README, seção "Segurança do Supabase — exposição
-- corrigida"): o Supabase expõe automaticamente todo o schema `public` por
-- uma API REST (PostgREST) e concede privilégios padrão aos papéis `anon`
-- e `authenticated`. O Django nunca usa essa API — conecta direto via
-- DATABASE_URL, autenticado como `postgres` — então esses grants só
-- servem para vazar dado por fora do sistema (já verificado na prática:
-- uma requisição REST com a chave `anon` chegou a devolver o hash de
-- senha de um usuário).
--
-- Esta correção foi aplicada manualmente uma vez, direto no SQL Editor do
-- Supabase, e nunca tinha ficado versionada — o que significa que
-- qualquer projeto Supabase novo (staging, uma cópia de teste, um restore
-- de backup) nasce SEM essa proteção até alguém lembrar de aplicar de
-- novo. Este script é essa aplicação, agora reproduzível.
--
-- Quando rodar: uma vez em qualquer projeto Supabase novo desta aplicação,
-- logo após a primeira `manage.py migrate`. Idempotente — rodar de novo
-- num projeto já protegido não tem efeito colateral.
--
-- Como rodar:
--   psql "$DATABASE_URL" -f scripts/supabase_hardening.sql
-- ou cole o conteúdo no SQL Editor do painel do Supabase.

-- 1) Revoga os privilégios padrão que o Supabase concede a `anon` e
--    `authenticated` sobre tudo que já existe no schema `public`.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON SCHEMA public FROM anon, authenticated;

-- 2) Garante que TABELAS NOVAS (a próxima `manage.py migrate`) não nasçam
--    com esses grants de novo — sem isto, cada migration que cria uma
--    tabela reabre a exposição para ela.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- 3) Liga Row Level Security em toda tabela do schema `public`, sem
--    nenhuma policy. RLS sem policy nega tudo para quem não é dono da
--    tabela — segunda barreira, caso um GRANT seja reconcedido por engano
--    no futuro. O Django não é afetado: conecta como dono das tabelas
--    (`postgres`), que tem BYPASSRLS.
--
--    Percorre `pg_tables` em vez de listar tabela por tabela: cobre
--    qualquer tabela criada por migration depois deste script, sem
--    precisar manter uma lista em dia.
DO $$
DECLARE
    tabela text;
BEGIN
    FOR tabela IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tabela);
    END LOOP;
END $$;
