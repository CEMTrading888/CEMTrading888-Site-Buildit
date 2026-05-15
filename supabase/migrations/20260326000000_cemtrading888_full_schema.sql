


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "public";






CREATE TYPE "public"."sandboxtype" AS ENUM (
    'E2B',
    'MODAL',
    'LOCAL'
);


ALTER TYPE "public"."sandboxtype" OWNER TO "postgres";


CREATE TYPE "public"."stepstatus" AS ENUM (
    'PENDING',
    'SUCCESS',
    'FAILED',
    'CANCELLED'
);


ALTER TYPE "public"."stepstatus" OWNER TO "postgres";


CREATE TYPE "public"."vectordbprovider" AS ENUM (
    'NATIVE',
    'TPUF',
    'PINECONE'
);


ALTER TYPE "public"."vectordbprovider" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."_queue_journal_for_embedding"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  INSERT INTO cem_embedding_queue (source_table, source_id, status)
  VALUES ('cem_eureka_journal', NEW.id, 'pending')
  ON CONFLICT (source_table, source_id)
  DO UPDATE SET status = 'pending', queued_at = now();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."_queue_journal_for_embedding"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."_queue_strategy_for_embedding"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  IF NEW.is_winner = true OR NEW.strategy_score > 60 THEN
    INSERT INTO cem_embedding_queue (source_table, source_id, status)
    VALUES ('cem_strategy_results', NEW.id, 'pending')
    ON CONFLICT (source_table, source_id)
    DO UPDATE SET status = 'pending', queued_at = now();
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."_queue_strategy_for_embedding"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."_update_strategy_fts"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.fts := to_tsvector('english',
    COALESCE(NEW.name, '') || ' ' ||
    COALESCE(NEW.asset, '') || ' ' ||
    COALESCE(NEW.timeframe, '') || ' ' ||
    COALESCE(NEW.market_condition, '') || ' ' ||
    COALESCE(NEW.tier, '') || ' ' ||
    COALESCE(NEW.filters::text, '') || ' ' ||
    COALESCE(NEW.signals::text, '') || ' ' ||
    COALESCE(NEW.risk_settings::text, '')
  );
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."_update_strategy_fts"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."cem_context_upsert_trigger"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- If key already exists, update it instead of inserting
  UPDATE cem_context 
  SET value = NEW.value,
      updated_by = NEW.updated_by,
      updated_at = NOW()
  WHERE key = NEW.key;
  
  -- If the update matched a row, cancel the insert
  IF FOUND THEN
    RETURN NULL; -- NULL cancels the INSERT
  END IF;
  
  -- Otherwise let the INSERT proceed normally
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."cem_context_upsert_trigger"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."fts_search_strategies"("query_text" "text", "match_count" integer DEFAULT 10, "asset_filter" "text" DEFAULT NULL::"text") RETURNS TABLE("id" "uuid", "name" "text", "asset" "text", "timeframe" "text", "signals" "jsonb", "risk_settings" "jsonb", "tier" "text", "fts_rank" double precision)
    LANGUAGE "plpgsql" STABLE
    AS $$
DECLARE
  tsq tsquery;
BEGIN
  -- Try exact websearch first (handles quoted phrases, AND/OR/-)
  BEGIN
    tsq := websearch_to_tsquery('english', query_text);
  EXCEPTION WHEN others THEN
    tsq := to_tsquery('english', 'trading');
  END;
  
  RETURN QUERY
  SELECT 
    s.id, s.name, s.asset, s.timeframe, s.signals, s.risk_settings, s.tier,
    ts_rank(s.fts, tsq)::float as fts_rank
  FROM cem_strategy_library s
  WHERE s.fts @@ tsq
    AND (asset_filter IS NULL OR s.asset ILIKE '%' || asset_filter || '%')
  
  UNION
  
  -- Also do ILIKE fallback for any word in query (catches partial matches)
  SELECT DISTINCT
    s.id, s.name, s.asset, s.timeframe, s.signals, s.risk_settings, s.tier,
    0.3::float as fts_rank
  FROM cem_strategy_library s
  WHERE (
    s.name ILIKE '%' || split_part(query_text,' ',1) || '%'
    OR s.asset ILIKE '%' || split_part(query_text,' ',1) || '%'
    OR s.name ILIKE '%' || split_part(query_text,' ',2) || '%'
  )
  AND (asset_filter IS NULL OR s.asset ILIKE '%' || asset_filter || '%')
  
  ORDER BY fts_rank DESC
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."fts_search_strategies"("query_text" "text", "match_count" integer, "asset_filter" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."hybrid_search_strategies"("query_text" "text", "query_embedding" "public"."vector" DEFAULT NULL::"public"."vector", "match_count" integer DEFAULT 10, "asset_filter" "text" DEFAULT NULL::"text") RETURNS TABLE("id" "uuid", "name" "text", "asset" "text", "timeframe" "text", "signals" "jsonb", "risk_settings" "jsonb", "filters" "jsonb", "market_condition" "text", "tier" "text", "fts_rank" double precision, "vector_score" double precision, "combined_score" double precision)
    LANGUAGE "sql" STABLE
    AS $$
WITH
fts_results AS (
  SELECT 
    s.id, s.name, s.asset, s.timeframe, s.signals,
    s.risk_settings, s.filters, s.market_condition, s.tier,
    ts_rank(s.fts, websearch_to_tsquery('english', query_text)) as fts_rank
  FROM cem_strategy_library s
  WHERE s.fts @@ websearch_to_tsquery('english', query_text)
    AND (asset_filter IS NULL OR s.asset ILIKE '%' || asset_filter || '%')
  ORDER BY fts_rank DESC LIMIT 25
),
vector_results AS (
  SELECT 
    s.id, s.name, s.asset, s.timeframe, s.signals,
    s.risk_settings, s.filters, s.market_condition, s.tier,
    1 - (s.embedding <=> query_embedding) as vector_score
  FROM cem_strategy_library s
  WHERE query_embedding IS NOT NULL
    AND s.embedding IS NOT NULL
    AND 1 - (s.embedding <=> query_embedding) > 0.60
    AND (asset_filter IS NULL OR s.asset ILIKE '%' || asset_filter || '%')
  ORDER BY s.embedding <=> query_embedding LIMIT 25
),
combined AS (
  SELECT
    COALESCE(f.id, v.id) as id,
    COALESCE(f.name, v.name) as name,
    COALESCE(f.asset, v.asset) as asset,
    COALESCE(f.timeframe, v.timeframe) as timeframe,
    COALESCE(f.signals, v.signals) as signals,
    COALESCE(f.risk_settings, v.risk_settings) as risk_settings,
    COALESCE(f.filters, v.filters) as filters,
    COALESCE(f.market_condition, v.market_condition) as market_condition,
    COALESCE(f.tier, v.tier) as tier,
    COALESCE(f.fts_rank, 0.0) as fts_rank,
    COALESCE(v.vector_score, 0.0) as vector_score,
    COALESCE(f.fts_rank, 0.0) * 0.4 + COALESCE(v.vector_score, 0.0) * 0.6 as combined_score
  FROM fts_results f
  FULL OUTER JOIN vector_results v ON f.id = v.id
)
SELECT * FROM combined ORDER BY combined_score DESC LIMIT match_count;
$$;


ALTER FUNCTION "public"."hybrid_search_strategies"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer, "asset_filter" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."insert_claude_batch"("data" "jsonb") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  INSERT INTO cem_conversations (user_id, session_id, role, content, tags, created_at)
  SELECT
    (item->>'user_id')::uuid,
    (item->>'session_id')::uuid,
    item->>'role',
    item->>'content',
    ARRAY(SELECT jsonb_array_elements_text(item->'tags')),
    (item->>'created_at')::timestamptz
  FROM jsonb_array_elements(data) AS item;
END;
$$;


ALTER FUNCTION "public"."insert_claude_batch"("data" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."invalidate_old_bots"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  IF NEW.is_active = true THEN
    UPDATE cem_bots
    SET 
      is_active = false,
      invalidated_at = now(),
      invalidated_reason = 'new_version_generated'
    WHERE 
      user_email = NEW.user_email
      AND asset = NEW.asset
      AND id != NEW.id
      AND is_active = true;
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."invalidate_old_bots"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_cem_episodes"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) RETURNS TABLE("id" "uuid", "created_at" timestamp with time zone, "session_id" "text", "user_message" "text", "assistant_response" "text", "tools_used" "text"[], "outcome" "text", "similarity" double precision)
    LANGUAGE "sql" STABLE
    AS $$
    SELECT id, created_at, session_id, user_message, assistant_response, tools_used, outcome, 1 - (embedding <=> query_embedding) AS similarity
    FROM cem_episodes WHERE embedding IS NOT NULL AND 1 - (embedding <=> query_embedding) > similarity_threshold
    ORDER BY embedding <=> query_embedding LIMIT LEAST(top_k, 200);
$$;


ALTER FUNCTION "public"."match_cem_episodes"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_cem_insights"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) RETURNS TABLE("id" "uuid", "created_at" timestamp with time zone, "insight" "text", "confidence" numeric, "source_observation_ids" "uuid"[], "tags" "text"[], "similarity" double precision)
    LANGUAGE "sql" STABLE
    AS $$
    SELECT id, created_at, insight, confidence, source_observation_ids, tags, 1 - (embedding <=> query_embedding) AS similarity
    FROM cem_insights WHERE embedding IS NOT NULL AND 1 - (embedding <=> query_embedding) > similarity_threshold
    ORDER BY embedding <=> query_embedding LIMIT LEAST(top_k, 200);
$$;


ALTER FUNCTION "public"."match_cem_insights"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_cem_knowledge"("query_embedding" "public"."vector", "match_threshold" double precision DEFAULT 0.72, "match_count" integer DEFAULT 8, "filter_community" boolean DEFAULT true) RETURNS TABLE("id" "uuid", "source_table" "text", "source_id" "uuid", "content" "text", "metadata" "jsonb", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.source_table,
    e.source_id,
    e.content,
    e.metadata,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM cem_knowledge_embeddings e
  WHERE
    (filter_community = false OR e.is_community = true)
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."match_cem_knowledge"("query_embedding" "public"."vector", "match_threshold" double precision, "match_count" integer, "filter_community" boolean) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_cem_observations"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) RETURNS TABLE("id" "uuid", "created_at" timestamp with time zone, "source" "text", "observation" "text", "tags" "text"[], "metadata" "jsonb", "similarity" double precision)
    LANGUAGE "sql" STABLE
    AS $$
    SELECT id, created_at, source, observation, tags, metadata, 1 - (embedding <=> query_embedding) AS similarity
    FROM cem_observations WHERE embedding IS NOT NULL AND 1 - (embedding <=> query_embedding) > similarity_threshold
    ORDER BY embedding <=> query_embedding LIMIT LEAST(top_k, 200);
$$;


ALTER FUNCTION "public"."match_cem_observations"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_cem_strategies"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) RETURNS TABLE("id" "uuid", "created_at" timestamp with time zone, "name" "text", "description" "text", "asset" "text", "timeframe" "text", "market_condition" "text", "tier" "text", "similarity" double precision)
    LANGUAGE "sql" STABLE
    AS $$
    SELECT id, created_at, name, description, asset, timeframe, market_condition, tier, 1 - (embedding <=> query_embedding) AS similarity
    FROM cem_strategies WHERE embedding IS NOT NULL AND 1 - (embedding <=> query_embedding) > similarity_threshold
    ORDER BY embedding <=> query_embedding LIMIT LEAST(top_k, 200);
$$;


ALTER FUNCTION "public"."match_cem_strategies"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_community_patterns"("query_embedding" "public"."vector", "match_count" integer DEFAULT 5, "min_confidence" "text" DEFAULT 'emerging'::"text") RETURNS TABLE("id" "uuid", "asset_class" "text", "param_signature" "jsonb", "avg_return" double precision, "confirmation_count" integer, "confidence_tier" "text", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    p.id,
    p.asset_class,
    p.strategy_params AS param_signature,
    p.return_pct AS avg_return,
    p.confirmation_count,
    p.confidence_tier,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM cem_pattern_library p
  WHERE p.embedding IS NOT NULL
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."match_community_patterns"("query_embedding" "public"."vector", "match_count" integer, "min_confidence" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_documents"("query_embedding" "public"."vector", "match_count" integer DEFAULT 5, "filter" "jsonb" DEFAULT '{}'::"jsonb") RETURNS TABLE("id" bigint, "content" "text", "metadata" "jsonb", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) AS similarity
  FROM documents d
  WHERE d.metadata @> filter
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."match_documents"("query_embedding" "public"."vector", "match_count" integer, "filter" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_user_memories"("query_embedding" "public"."vector", "match_user_id" "text", "match_count" integer DEFAULT 5) RETURNS TABLE("id" "uuid", "content" "text", "memory_type" "text", "asset_class" "text", "importance_score" double precision, "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    m.id,
    m.content,
    m.memory_type,
    m.asset_class,
    m.importance_score,
    1 - (m.embedding <=> query_embedding) AS similarity
  FROM cem_user_memory m
  WHERE m.user_id = match_user_id
    AND m.embedding IS NOT NULL
  ORDER BY m.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."match_user_memories"("query_embedding" "public"."vector", "match_user_id" "text", "match_count" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_brain"("query_embedding" "public"."vector", "match_count" integer DEFAULT 5, "min_similarity" double precision DEFAULT 0.5) RETURNS TABLE("key" "text", "value" "text", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.key,
    LEFT(c.value, 500) as value,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM cem_context c
  WHERE c.embedding IS NOT NULL
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."search_brain"("query_embedding" "public"."vector", "match_count" integer, "min_similarity" double precision) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_knowledge"("query_embedding" "public"."vector", "match_count" integer DEFAULT 5, "source_filter" "text" DEFAULT NULL::"text") RETURNS TABLE("id" "uuid", "title" "text", "content" "text", "source_type" "text", "source_name" "text", "importance_score" double precision, "topic_tags" "text"[], "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    k.id,
    k.title,
    LEFT(k.content, 500) as content,
    k.source_type,
    k.source_name,
    k.importance_score,
    k.topic_tags,
    1 - (k.embedding <=> query_embedding) AS similarity
  FROM cem_knowledge_base k
  WHERE k.embedding IS NOT NULL
    AND (source_filter IS NULL OR k.source_type = source_filter)
  ORDER BY k.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


ALTER FUNCTION "public"."search_knowledge"("query_embedding" "public"."vector", "match_count" integer, "source_filter" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_library"("query_embedding" "public"."vector", "match_table" "text" DEFAULT 'cem_strategy_library'::"text", "match_count" integer DEFAULT 10) RETURNS TABLE("id" "uuid", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  IF match_table = 'cem_strategy_library' THEN
    RETURN QUERY
      SELECT s.id, 1 - (s.embedding <=> query_embedding) AS similarity
      FROM cem_strategy_library s
      WHERE s.embedding IS NOT NULL
      ORDER BY s.embedding <=> query_embedding
      LIMIT match_count;
  ELSIF match_table = 'cem_eureka_journal' THEN
    RETURN QUERY
      SELECT e.id, 1 - (e.embedding <=> query_embedding) AS similarity
      FROM cem_eureka_journal e
      WHERE e.embedding IS NOT NULL
      ORDER BY e.embedding <=> query_embedding
      LIMIT match_count;
  END IF;
END;
$$;


ALTER FUNCTION "public"."search_library"("query_embedding" "public"."vector", "match_table" "text", "match_count" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."unified_knowledge_search"("query_text" "text", "match_count" integer DEFAULT 8) RETURNS TABLE("source" "text", "content" "text", "score" double precision, "metadata" "jsonb")
    LANGUAGE "sql" STABLE
    AS $_$
WITH
strategy_hits AS (
  SELECT 
    'strategy_library' as source,
    s.name || ' | Asset: ' || s.asset || ' | TF: ' || s.timeframe || 
      ' | Tier: ' || COALESCE(s.tier,'open') ||
      ' | Signals: ' || COALESCE(s.signals::text,'{}') ||
      ' | Settings: ' || COALESCE(s.risk_settings::text,'{}') as content,
    f.fts_rank::float as score,
    jsonb_build_object('name', s.name, 'asset', s.asset,
                       'timeframe', s.timeframe, 'tier', s.tier,
                       'type', 'strategy') as metadata
  FROM fts_search_strategies(query_text, 5) f
  JOIN cem_strategy_library s ON s.id = f.id
),
research_hits AS (
  SELECT
    'coach_research' as source,
    COALESCE(title,'') || ': ' || COALESCE(summary,'') as content,
    0.7::float as score,
    jsonb_build_object('asset', asset, 'after_wr', after_wr,
                       'type', 'research_finding') as metadata
  FROM cem_coach_research
  WHERE summary IS NOT NULL
    AND (title ILIKE '%' || split_part(query_text,' ',1) || '%'
      OR asset ILIKE '%' || split_part(query_text,' ',1) || '%'
      OR summary ILIKE '%' || split_part(query_text,' ',1) || '%')
  LIMIT 3
),
journal_hits AS (
  SELECT
    'journal' as source,
    content,
    0.4::float as score,
    jsonb_build_object('type', 'journal_entry') as metadata
  FROM cem_knowledge_embeddings
  WHERE source_table = 'cem_eureka_journal'
    AND (content ILIKE '%' || split_part(query_text,' ',1) || '%'
      OR content ILIKE '%' || split_part(query_text,' ',2) || '%')
  LIMIT 2
),
mirror_hits AS (
  SELECT
    'mirror_live' as source,
    'Mirror Bot: ' || direction || ' ' || asset || 
      ' via ' || strategy_name || ' @ ' || entry_price::text || 
      ' | P&L $' || COALESCE(pnl_usd::text,'0') as content,
    0.65::float as score,
    jsonb_build_object('type','live_trade','asset',asset,
                       'strategy',strategy_name) as metadata
  FROM cem_live_trades
  WHERE status = 'open'
    AND (asset ILIKE '%' || split_part(query_text,' ',1) || '%'
      OR strategy_name ILIKE '%' || split_part(query_text,' ',1) || '%')
  LIMIT 2
)
SELECT * FROM strategy_hits
UNION ALL SELECT * FROM research_hits
UNION ALL SELECT * FROM journal_hits
UNION ALL SELECT * FROM mirror_hits
ORDER BY score DESC
LIMIT match_count;
$_$;


ALTER FUNCTION "public"."unified_knowledge_search"("query_text" "text", "match_count" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_academy_leaderboard"() RETURNS "void"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- Win rate leaders (weekly, min 10 trades)
  INSERT INTO cem_academy_leaderboard (user_id, strategy_id, period, category, score, win_rate, return_pct, total_trades, asset, updated_at)
  SELECT 
    s.user_id, s.id, 'weekly', 'win_rate',
    s.win_rate, s.win_rate, s.total_return, s.total_trades, s.asset,
    now()
  FROM cem_academy_strategies s
  WHERE s.total_trades >= 10 AND s.updated_at > now() - interval '7 days'
  ON CONFLICT (user_id, period, category) 
  DO UPDATE SET score = EXCLUDED.score, updated_at = now();
END;
$$;


ALTER FUNCTION "public"."update_academy_leaderboard"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_cem_decisions_timestamp"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_cem_decisions_timestamp"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."upsert_brain"("p_key" "text", "p_value" "text", "p_updated_by" "text" DEFAULT 'claude'::"text") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  INSERT INTO cem_context (key, value, updated_by)
  VALUES (p_key, p_value, p_updated_by)
  ON CONFLICT (key) DO UPDATE
  SET value = EXCLUDED.value,
      updated_by = EXCLUDED.updated_by;
END;
$$;


ALTER FUNCTION "public"."upsert_brain"("p_key" "text", "p_value" "text", "p_updated_by" "text") OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."agent_environment_variables" (
    "id" character varying NOT NULL,
    "key" character varying NOT NULL,
    "value" character varying NOT NULL,
    "description" character varying,
    "value_enc" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."agent_environment_variables" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."agents" (
    "id" character varying NOT NULL,
    "agent_type" character varying,
    "name" character varying,
    "description" character varying,
    "system" character varying,
    "message_ids" json,
    "response_format" json,
    "metadata_" json,
    "llm_config" json,
    "embedding_config" json,
    "compaction_settings" json,
    "tool_rules" json,
    "message_buffer_autoclear" boolean NOT NULL,
    "enable_sleeptime" boolean,
    "last_run_completion" timestamp with time zone,
    "last_run_duration_ms" integer,
    "last_stop_reason" character varying,
    "timezone" character varying,
    "max_files_open" integer,
    "per_file_view_window_char_limit" integer,
    "hidden" boolean,
    "_vector_db_namespace" character varying,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "project_id" character varying,
    "entity_id" character varying,
    "base_template_id" character varying,
    "template_id" character varying,
    "deployment_id" character varying
);


ALTER TABLE "public"."agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."agents_tags" (
    "agent_id" character varying NOT NULL,
    "tag" character varying NOT NULL
);


ALTER TABLE "public"."agents_tags" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."archival_passages" (
    "id" character varying NOT NULL,
    "text" character varying NOT NULL,
    "embedding_config" json,
    "metadata_" json NOT NULL,
    "tags" json,
    "embedding" "public"."vector"(4096),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "archive_id" character varying NOT NULL
);


ALTER TABLE "public"."archival_passages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."archives" (
    "id" character varying NOT NULL,
    "name" character varying NOT NULL,
    "description" character varying,
    "vector_db_provider" "public"."vectordbprovider" NOT NULL,
    "embedding_config" json,
    "metadata_" json,
    "_vector_db_namespace" character varying,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."archives" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."archives_agents" (
    "agent_id" character varying NOT NULL,
    "archive_id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT '2026-05-10 01:32:15.336839+00'::timestamp with time zone NOT NULL,
    "is_owner" boolean NOT NULL
);


ALTER TABLE "public"."archives_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."block" (
    "template_name" character varying,
    "description" character varying,
    "label" character varying NOT NULL,
    "is_template" boolean NOT NULL,
    "preserve_on_migration" boolean,
    "value" character varying NOT NULL,
    "limit" integer NOT NULL,
    "metadata_" json,
    "read_only" boolean NOT NULL,
    "hidden" boolean,
    "current_history_entry_id" character varying,
    "version" integer DEFAULT 1 NOT NULL,
    "organization_id" character varying NOT NULL,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "project_id" character varying,
    "entity_id" character varying,
    "base_template_id" character varying,
    "template_id" character varying,
    "deployment_id" character varying
);


ALTER TABLE "public"."block" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."block_history" (
    "id" character varying NOT NULL,
    "description" "text",
    "label" character varying NOT NULL,
    "value" "text" NOT NULL,
    "limit" bigint NOT NULL,
    "metadata_" json,
    "actor_type" character varying,
    "actor_id" character varying,
    "block_id" character varying NOT NULL,
    "sequence_number" integer NOT NULL,
    "organization_id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."block_history" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."blocks_agents" (
    "agent_id" character varying NOT NULL,
    "block_id" character varying NOT NULL,
    "block_label" character varying NOT NULL
);


ALTER TABLE "public"."blocks_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."blocks_conversations" (
    "conversation_id" character varying NOT NULL,
    "block_id" character varying NOT NULL,
    "block_label" character varying NOT NULL
);


ALTER TABLE "public"."blocks_conversations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."blocks_tags" (
    "block_id" character varying NOT NULL,
    "tag" character varying NOT NULL,
    "organization_id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."blocks_tags" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_delivery_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "order_id" "uuid",
    "user_id" "uuid",
    "tier" "text" NOT NULL,
    "customer_email" "text",
    "status" "text" DEFAULT 'queued'::"text",
    "bot_code" "text",
    "validation_result" "jsonb" DEFAULT '{}'::"jsonb",
    "delivery_result" "jsonb" DEFAULT '{}'::"jsonb",
    "error_message" "text",
    "retry_count" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "pipeline_status" "jsonb" DEFAULT '{}'::"jsonb",
    "generating_started_at" timestamp with time zone,
    "generating_completed_at" timestamp with time zone,
    "validating_started_at" timestamp with time zone,
    "validating_completed_at" timestamp with time zone,
    "delivering_started_at" timestamp with time zone,
    "delivering_completed_at" timestamp with time zone
);


ALTER TABLE "public"."bot_delivery_jobs" OWNER TO "postgres";


COMMENT ON TABLE "public"."bot_delivery_jobs" IS 'Bot delivery queue — tracks fulfillment of purchased bots to brokers.';



CREATE TABLE IF NOT EXISTS "public"."cem_account_trades" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "account_id" "uuid",
    "user_id" "uuid",
    "trade_source" "text" DEFAULT 'manual'::"text" NOT NULL,
    "direction" "text" NOT NULL,
    "asset" "text" NOT NULL,
    "entry_price" numeric(12,4),
    "exit_price" numeric(12,4),
    "quantity" numeric(8,4) DEFAULT 1,
    "pnl" numeric(12,2),
    "rr_achieved" numeric(6,4),
    "entry_bar" integer,
    "exit_bar" integer,
    "entry_at" timestamp with time zone,
    "exit_at" timestamp with time zone,
    "exit_reason" "text",
    "strategy_id" "uuid",
    "copied_from_user_id" "uuid",
    "cem_note" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_account_trades" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_beta_invites" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "code" "text" NOT NULL,
    "created_by" "text" DEFAULT 'chandler'::"text",
    "used_by" "uuid",
    "used_at" timestamp with time zone,
    "tier_granted" "text" DEFAULT 'member'::"text",
    "max_uses" integer DEFAULT 1,
    "uses_count" integer DEFAULT 0,
    "expires_at" timestamp with time zone,
    "active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "label" "text"
);


ALTER TABLE "public"."cem_beta_invites" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_bot_heartbeats" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "channel_id" "text" NOT NULL,
    "last_beat" timestamp with time zone DEFAULT "now"(),
    "status" "text" DEFAULT 'running'::"text",
    "open_positions" integer DEFAULT 0,
    "trades_last_hour" integer DEFAULT 0,
    "error_msg" "text",
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_bot_heartbeats" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_bot_performance" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "strategy_id" "uuid",
    "bot_delivery_id" "uuid",
    "broker" "text",
    "is_prop_firm" boolean DEFAULT false,
    "prop_firm_name" "text",
    "period_start" "date",
    "period_end" "date",
    "live_return_pct" numeric(8,3),
    "live_win_rate" numeric(5,3),
    "live_sharpe" numeric(6,3),
    "live_trades" integer,
    "passed_challenge" boolean,
    "notes" "text",
    "reported_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_bot_performance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_bots" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "user_email" "text" NOT NULL,
    "bot_token" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "strategy_name" "text",
    "asset" "text",
    "timeframe" "text",
    "is_active" boolean DEFAULT true NOT NULL,
    "invalidated_at" timestamp with time zone,
    "invalidated_reason" "text",
    "last_heartbeat" timestamp with time zone,
    "heartbeat_count" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "delivered_at" timestamp with time zone,
    "notes" "text"
);


ALTER TABLE "public"."cem_bots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_live_trades" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "session_id" "text",
    "asset" "text" NOT NULL,
    "strategy_name" "text",
    "direction" "text" NOT NULL,
    "entry_price" numeric,
    "exit_price" numeric,
    "entry_time" timestamp with time zone,
    "exit_time" timestamp with time zone,
    "duration_minutes" integer,
    "pnl_usd" numeric DEFAULT 0,
    "pnl_pct" numeric DEFAULT 0,
    "contract_mult" numeric DEFAULT 1,
    "status" "text" DEFAULT 'open'::"text",
    "is_winner" boolean,
    "notes" "text",
    "chart_snapshot" "text",
    "stop_loss" numeric,
    "take_profit" numeric,
    "exit_reason" character varying(20),
    "account_size" integer,
    "position_size_usd" numeric,
    "account_id" "text",
    "regime" "text",
    "channel_id" "text" DEFAULT 'crypto_24_7'::"text"
);


ALTER TABLE "public"."cem_live_trades" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."cem_channel_performance" AS
 SELECT "channel_id",
    "count"(*) FILTER (WHERE ("status" = 'closed'::"text")) AS "total_trades",
    "count"(*) FILTER (WHERE ("status" = 'open'::"text")) AS "open_positions",
    "round"(("avg"(
        CASE
            WHEN ("is_winner" AND ("status" = 'closed'::"text")) THEN 1.0
            ELSE 0.0
        END) * (100)::numeric), 1) AS "win_rate",
    "round"("sum"(
        CASE
            WHEN ("status" = 'closed'::"text") THEN COALESCE("pnl_usd", (0)::numeric)
            ELSE (0)::numeric
        END), 2) AS "total_pnl",
    "count"(DISTINCT "strategy_name") AS "strategies_tested",
    "count"(DISTINCT "asset") AS "assets_covered",
    "max"("created_at") AS "last_activity"
   FROM "public"."cem_live_trades"
  GROUP BY "channel_id";


ALTER VIEW "public"."cem_channel_performance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_coach_research" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "session_id" "text",
    "asset" "text",
    "timeframe" "text",
    "discovery_type" "text",
    "title" "text" NOT NULL,
    "summary" "text",
    "evidence" "text",
    "before_wr" numeric,
    "after_wr" numeric,
    "params_before" "jsonb",
    "params_after" "jsonb",
    "was_useful" boolean,
    "source" "text" DEFAULT 'autonomous_coach'::"text",
    "screenshot_b64" "text",
    "reasoning" "text",
    "market_conditions" character varying(50),
    "screenshot_url" "text",
    "strategy_name" "text",
    "fts" "tsvector"
);


ALTER TABLE "public"."cem_coach_research" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_community_follows" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "follower_id" "uuid",
    "following_id" "uuid",
    "cem_vetting_score" numeric(5,2),
    "cem_vetting_note" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_community_follows" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_community_insights" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "eureka_id" "uuid",
    "asset" "text",
    "category" "text",
    "headline" "text" NOT NULL,
    "detail" "text" NOT NULL,
    "votes_up" integer DEFAULT 0,
    "votes_down" integer DEFAULT 0,
    "is_featured" boolean DEFAULT false,
    "featured_week" "date",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_community_insights_category_check" CHECK (("category" = ANY (ARRAY['signal'::"text", 'filter'::"text", 'risk'::"text", 'psychology'::"text", 'combination'::"text"])))
);


ALTER TABLE "public"."cem_community_insights" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_community_posts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "post_type" "text" DEFAULT 'trade'::"text" NOT NULL,
    "content" "text",
    "trade_id" "uuid",
    "account_id" "uuid",
    "pnl_shown" numeric(12,2),
    "asset" "text",
    "strategy_name" "text",
    "is_verified" boolean DEFAULT false,
    "likes" integer DEFAULT 0,
    "comments" integer DEFAULT 0,
    "copies" integer DEFAULT 0,
    "is_copyable" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_community_posts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_strategy_results" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "text",
    "user_handle" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "asset_class" "text",
    "asset" "text",
    "timeframe" "text",
    "period" "text",
    "parameters" "jsonb",
    "estimate_win_rate_low" numeric,
    "estimate_win_rate_high" numeric,
    "estimate_trades_per_day_low" numeric,
    "estimate_trades_per_day_high" numeric,
    "estimate_rr" numeric,
    "estimate_signal_strength" integer,
    "estimate_risk_level" "text",
    "total_return" numeric,
    "sharpe_ratio" numeric,
    "max_drawdown" numeric,
    "win_rate" numeric,
    "total_trades" integer,
    "alpha" numeric,
    "beta" numeric,
    "strategy_score" numeric,
    "result_tag" "text",
    "is_winner" boolean DEFAULT false,
    "submitted_to_marketplace" boolean DEFAULT false,
    "user_xp_at_run" integer,
    "paper_pnl_usd" numeric DEFAULT 0,
    "strategy_name" "text",
    "is_favorite" boolean DEFAULT false,
    "profit_factor" numeric
);


ALTER TABLE "public"."cem_strategy_results" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_strategy_results" IS 'Backtest results logged from the platform — strategy performance history.';



CREATE OR REPLACE VIEW "public"."cem_community_stats" AS
 SELECT "asset",
    "timeframe",
    "count"(*) AS "total_backtests",
    "round"("avg"("win_rate"), 1) AS "avg_win_rate",
    "round"("avg"("sharpe_ratio"), 2) AS "avg_sharpe",
    "round"("avg"("total_return"), 2) AS "avg_return",
    "max"("strategy_score") AS "best_score",
    "count"(*) FILTER (WHERE ("is_winner" = true)) AS "winner_count",
    "max"("created_at") AS "last_updated"
   FROM "public"."cem_strategy_results"
  WHERE ("total_trades" >= 5)
  GROUP BY "asset", "timeframe"
  ORDER BY ("count"(*) FILTER (WHERE ("is_winner" = true))) DESC, ("round"("avg"("sharpe_ratio"), 2)) DESC;


ALTER VIEW "public"."cem_community_stats" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_congress_live" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "league_id" integer DEFAULT 1 NOT NULL,
    "member_name" "text" NOT NULL,
    "party" "text",
    "ticker" "text" NOT NULL,
    "action" "text" NOT NULL,
    "amount_range" "text",
    "report_date" "text",
    "paper_entry_price" numeric(12,4) DEFAULT 0,
    "paper_current_price" numeric(12,4) DEFAULT 0,
    "paper_pnl" numeric(12,2) DEFAULT 0,
    "signal_fired_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_congress_live_action_check" CHECK (("action" = ANY (ARRAY['buy'::"text", 'sell'::"text"])))
);


ALTER TABLE "public"."cem_congress_live" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_context" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "updated_by" "text" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "embedding" "public"."vector"(1536)
);


ALTER TABLE "public"."cem_context" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_context" IS 'THE BRAIN — key/value store for all AI memory, task queue, platform config. The only table Claude actively reads and writes.';



CREATE TABLE IF NOT EXISTS "public"."cem_conversations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "session_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "content" "text" NOT NULL,
    "strategy_id" "uuid",
    "asset" "text",
    "tags" "text"[],
    "embedding" "public"."vector"(1536),
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_conversations_role_check" CHECK (("role" = ANY (ARRAY['user'::"text", 'assistant'::"text", 'system'::"text"])))
);


ALTER TABLE "public"."cem_conversations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_curriculum_connections" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "instance_a" "uuid",
    "instance_b" "uuid",
    "connection_type" "text",
    "strength" "text" DEFAULT 'medium'::"text",
    "notes" "text"
);


ALTER TABLE "public"."cem_curriculum_connections" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_curriculum_instances" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "node_id" "uuid",
    "path" "text",
    "asset" "text" NOT NULL,
    "asset_class" "text",
    "timeframe" "text",
    "strategy_name" "text",
    "condition_name" "text",
    "entry_logic" "text",
    "exit_logic" "text",
    "filters" "text"[],
    "win_rate" numeric,
    "profit_factor" numeric,
    "total_trades" integer,
    "total_return" numeric,
    "max_drawdown" numeric,
    "avg_rr" numeric,
    "sharpe_ratio" numeric,
    "date_confirmed" "date",
    "sample_period" "text",
    "notes" "text",
    "also_works_on" "text"[],
    "does_not_work_on" "text"[],
    "is_winner" boolean DEFAULT false,
    "is_live_trading" boolean DEFAULT false,
    "confidence" "text" DEFAULT 'medium'::"text",
    "status" "text" DEFAULT 'TESTING'::"text",
    "optimization_attempts" integer DEFAULT 0,
    "filters_applied" "text"[] DEFAULT '{}'::"text"[],
    "threshold_met_at" timestamp with time zone,
    "visibility_tier" integer DEFAULT 2,
    "reveal_after_days" integer DEFAULT 0,
    "parameters_locked" boolean DEFAULT true,
    "chart_snapshot_url" "text",
    "eureka_note" "text",
    "coach_thought_process" "text",
    "visual_library_ready" boolean DEFAULT false
);


ALTER TABLE "public"."cem_curriculum_instances" OWNER TO "postgres";


COMMENT ON COLUMN "public"."cem_curriculum_instances"."visibility_tier" IS '0=internal, 1=free/stream, 2=beta($39.99), 3=member($79.99), 4=pro($97), 5=bot';



CREATE TABLE IF NOT EXISTS "public"."cem_curriculum_nodes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "level" "text" NOT NULL,
    "parent_id" "uuid",
    "path" "text",
    "name" "text" NOT NULL,
    "slug" "text" NOT NULL,
    "description" "text",
    "total_instances" integer DEFAULT 0,
    "avg_win_rate" numeric,
    "avg_profit_factor" numeric,
    "best_win_rate" numeric,
    "best_asset" "text",
    "best_timeframe" "text",
    "tags" "text"[] DEFAULT '{}'::"text"[],
    "icon" "text",
    "is_active" boolean DEFAULT true,
    "sort_order" integer DEFAULT 0
);


ALTER TABLE "public"."cem_curriculum_nodes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_decisions" (
    "id" integer NOT NULL,
    "topic" "text" NOT NULL,
    "category" "text" NOT NULL,
    "current_decision" "text" NOT NULL,
    "history" "jsonb" DEFAULT '[]'::"jsonb",
    "locked" boolean DEFAULT true,
    "locked_by" "text" DEFAULT 'Chandler'::"text",
    "locked_date" "date" NOT NULL,
    "brain_keys" "text"[],
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_decisions" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_decisions_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_decisions_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_decisions_id_seq" OWNED BY "public"."cem_decisions"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_embedding_queue" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_table" "text" NOT NULL,
    "source_id" "uuid" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "error_msg" "text",
    "queued_at" timestamp with time zone DEFAULT "now"(),
    "processed_at" timestamp with time zone
);


ALTER TABLE "public"."cem_embedding_queue" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_episodes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "cycle_timestamp" timestamp with time zone DEFAULT "now"(),
    "cycle_number" bigint,
    "regime_context" "jsonb" DEFAULT '{}'::"jsonb",
    "reasoning_trace" "jsonb" DEFAULT '{}'::"jsonb",
    "actions_taken" "jsonb" DEFAULT '[]'::"jsonb",
    "outcomes" "jsonb" DEFAULT '{}'::"jsonb",
    "strategies_tested" "uuid"[] DEFAULT '{}'::"uuid"[],
    "strategies_deployed" "uuid"[] DEFAULT '{}'::"uuid"[],
    "viewer_interactions" "jsonb" DEFAULT '[]'::"jsonb",
    "episode_metrics" "jsonb" DEFAULT '{}'::"jsonb",
    "importance_score" integer DEFAULT 5,
    "distilled_to_insight_id" "uuid",
    "distillation_timestamp" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "embedding" "public"."vector"(1536),
    "session_id" "text",
    "user_message" "text",
    "assistant_response" "text",
    "tools_used" "text"[],
    "outcome" "text",
    CONSTRAINT "cem_episodes_importance_score_check" CHECK ((("importance_score" >= 1) AND ("importance_score" <= 10)))
);


ALTER TABLE "public"."cem_episodes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_eureka_journal" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "session_id" "uuid",
    "strategy_id" "uuid",
    "asset" "text",
    "timeframe" "text",
    "eureka_type" "text",
    "title" "text" NOT NULL,
    "insight" "text" NOT NULL,
    "before_metric" "jsonb",
    "after_metric" "jsonb",
    "is_community" boolean DEFAULT false,
    "community_votes" integer DEFAULT 0,
    "embedding" "public"."vector"(1536),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "local_id" "text",
    "category" "text" DEFAULT 'general'::"text",
    "difficulty" "text" DEFAULT 'beginner'::"text",
    "course_ready" boolean DEFAULT false,
    "chapter" integer DEFAULT 0,
    "screenshot_b64" "text",
    "screenshot_url" "text",
    "entry_price" numeric,
    "stop_loss" numeric,
    "take_profit" numeric,
    "is_public_preview" boolean DEFAULT false,
    "source" "text" DEFAULT 'coach_autonomous'::"text",
    "journal_number" integer NOT NULL,
    "insight_note_id" "uuid",
    "replay_bar_index" integer,
    "replay_symbol" character varying(20),
    "replay_interval" character varying(10),
    "indicator_values" "jsonb",
    "lesson_id" integer,
    "visibility_tier" integer DEFAULT 2,
    "parameters_locked" boolean DEFAULT true,
    "chart_snapshot" "jsonb",
    CONSTRAINT "cem_eureka_journal_eureka_type_check" CHECK (("eureka_type" = ANY (ARRAY['coach'::"text", 'signal'::"text", 'backtest'::"text", 'mine'::"text", 'shot'::"text", 'user'::"text", 'filter'::"text", 'risk'::"text", 'session'::"text", 'combination'::"text", 'mindset'::"text", 'screenshot'::"text"])))
);


ALTER TABLE "public"."cem_eureka_journal" OWNER TO "postgres";


COMMENT ON COLUMN "public"."cem_eureka_journal"."local_id" IS 'Client-generated ID from localStorage (format: j_timestamp_random). Used to prevent duplicate syncs.';



CREATE SEQUENCE IF NOT EXISTS "public"."cem_eureka_journal_journal_number_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_eureka_journal_journal_number_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_eureka_journal_journal_number_seq" OWNED BY "public"."cem_eureka_journal"."journal_number";



CREATE TABLE IF NOT EXISTS "public"."cem_github_staging" (
    "id" integer NOT NULL,
    "file_path" "text" NOT NULL,
    "content" "text" NOT NULL,
    "file_order" integer DEFAULT 0,
    "status" "text" DEFAULT 'staged'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."cem_github_staging" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_github_staging" IS 'GitHub build staging area — Claude inserts file_path + content, CEM pulls and commits to GitHub';



CREATE SEQUENCE IF NOT EXISTS "public"."cem_github_staging_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_github_staging_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_github_staging_id_seq" OWNED BY "public"."cem_github_staging"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_indicator_isolation" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "asset" "text" NOT NULL,
    "strategy_name" "text" NOT NULL,
    "regime" "text",
    "timeframe" "text" DEFAULT '15m'::"text",
    "isolation_results" "jsonb",
    "combo_results" "jsonb",
    "best_combo" "jsonb",
    "worst_addition" "text",
    "comparison_note" "text",
    "visibility_tier" integer DEFAULT 3,
    "is_course_ready" boolean DEFAULT false
);


ALTER TABLE "public"."cem_indicator_isolation" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_indicator_isolation" IS 'Indicator isolation + combination testing results. Each row = one full analysis of which indicators contribute to a strategy and why.';



CREATE TABLE IF NOT EXISTS "public"."cem_insight_notes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "session_date" "date" DEFAULT CURRENT_DATE,
    "asset" "text" NOT NULL,
    "asset_class" "text",
    "strategy_name" "text",
    "timeframe" "text",
    "note_type" "text" NOT NULL,
    "headline" "text" NOT NULL,
    "body" "text" NOT NULL,
    "metrics" "jsonb" DEFAULT '{}'::"jsonb",
    "related_assets" "text"[] DEFAULT '{}'::"text"[],
    "tags" "text"[] DEFAULT '{}'::"text"[],
    "confidence" "text" DEFAULT 'medium'::"text",
    "market_conditions" "text",
    "coach_session_id" "text",
    "is_verified" boolean DEFAULT false,
    "is_course_ready" boolean DEFAULT false,
    "upvotes" integer DEFAULT 0,
    "curriculum_node_id" "uuid",
    "curriculum_instance_id" "uuid",
    "chart_snapshot" "jsonb",
    "visibility_tier" integer DEFAULT 2
);


ALTER TABLE "public"."cem_insight_notes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_insights" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "title" "text",
    "content" "text",
    "insight_type" "text",
    "importance_score" integer DEFAULT 5,
    "source_observations" "uuid"[] DEFAULT '{}'::"uuid"[],
    "source_strategies" "uuid"[] DEFAULT '{}'::"uuid"[],
    "source_episodes" "uuid"[] DEFAULT '{}'::"uuid"[],
    "related_insight_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    "prerequisite_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    "contradicts_ids" "uuid"[] DEFAULT '{}'::"uuid"[],
    "tags" "text"[] DEFAULT '{}'::"text"[],
    "confidence" numeric(4,3) DEFAULT 0.5,
    "verification_count" integer DEFAULT 0,
    "last_verified_at" timestamp with time zone,
    "access_count" integer DEFAULT 0,
    "last_accessed" timestamp with time zone DEFAULT "now"(),
    "generation" integer DEFAULT 1,
    "superseded_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "embedding" "public"."vector"(1536),
    "insight" "text",
    "source_observation_ids" "uuid"[],
    "compiled_from" "uuid"[],
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    CONSTRAINT "cem_insights_confidence_check" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "cem_insights_importance_score_check" CHECK ((("importance_score" >= 1) AND ("importance_score" <= 10))),
    CONSTRAINT "cem_insights_insight_type_check" CHECK (("insight_type" = ANY (ARRAY['strategy_pattern'::"text", 'regime_correlation'::"text", 'risk_lesson'::"text", 'execution_principle'::"text", 'market_structure'::"text", 'hypothesis_falsified'::"text"])))
);


ALTER TABLE "public"."cem_insights" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_invite_codes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "code" "text" NOT NULL,
    "tier" "text" DEFAULT 'beta'::"text" NOT NULL,
    "max_uses" integer DEFAULT 1,
    "uses_remaining" integer DEFAULT 1,
    "used_by" "jsonb" DEFAULT '[]'::"jsonb",
    "expires_at" timestamp with time zone,
    "created_by" "text" DEFAULT 'chandler'::"text",
    "label" "text",
    "is_active" boolean DEFAULT true,
    "notes" "text"
);


ALTER TABLE "public"."cem_invite_codes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_knowledge_embeddings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_table" "text" NOT NULL,
    "source_id" "uuid" NOT NULL,
    "content" "text" NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "is_community" boolean DEFAULT false,
    "embedding" "public"."vector"(1536),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_knowledge_embeddings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_known_fixes" (
    "id" integer NOT NULL,
    "problem" "text" NOT NULL,
    "fix" "text" NOT NULL,
    "category" "text" NOT NULL,
    "discovered_date" "date" DEFAULT CURRENT_DATE,
    "still_applies" boolean DEFAULT true,
    "notes" "text",
    "example" "text"
);


ALTER TABLE "public"."cem_known_fixes" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_known_fixes_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_known_fixes_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_known_fixes_id_seq" OWNED BY "public"."cem_known_fixes"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_library_lessons" (
    "id" integer NOT NULL,
    "title" "text" NOT NULL,
    "description" "text",
    "pattern_type" "text",
    "difficulty" "text" DEFAULT 'beginner'::"text",
    "entry_count" integer DEFAULT 0,
    "order_index" integer DEFAULT 0,
    "is_published" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_library_lessons" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_library_lessons_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_library_lessons_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_library_lessons_id_seq" OWNED BY "public"."cem_library_lessons"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_links" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "source_id" "uuid" NOT NULL,
    "source_table" "text" NOT NULL,
    "target_id" "uuid" NOT NULL,
    "target_table" "text" NOT NULL,
    "link_type" "text" DEFAULT 'relates_to'::"text" NOT NULL,
    "strength" double precision DEFAULT 0.5 NOT NULL,
    "context" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "cem_links_link_type_check" CHECK (("link_type" = ANY (ARRAY['relates_to'::"text", 'supports'::"text", 'contradicts'::"text", 'derived_from'::"text", 'mentions'::"text", 'similar_to'::"text", 'causes'::"text"]))),
    CONSTRAINT "cem_links_source_table_check" CHECK (("source_table" = ANY (ARRAY['cem_observations'::"text", 'cem_insights'::"text", 'cem_episodes'::"text", 'cem_strategies'::"text", 'cem_context'::"text"]))),
    CONSTRAINT "cem_links_strength_check" CHECK ((("strength" >= (0.0)::double precision) AND ("strength" <= (1.0)::double precision))),
    CONSTRAINT "cem_links_target_table_check" CHECK (("target_table" = ANY (ARRAY['cem_observations'::"text", 'cem_insights'::"text", 'cem_episodes'::"text", 'cem_strategies'::"text", 'cem_context'::"text"])))
);


ALTER TABLE "public"."cem_links" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_market_snapshots" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "asset" "text" NOT NULL,
    "snapshot_date" "date" NOT NULL,
    "condition" "text",
    "adr_pct" numeric(6,3),
    "volume_vs_avg" numeric(6,3),
    "adx_value" numeric(6,2),
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_market_snapshots_condition_check" CHECK (("condition" = ANY (ARRAY['trending_up'::"text", 'trending_down'::"text", 'ranging'::"text", 'volatile'::"text", 'low_volume'::"text"])))
);


ALTER TABLE "public"."cem_market_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_marketplace_listings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "seller_id" "uuid",
    "listing_type" "text" DEFAULT 'strategy'::"text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "price_monthly" numeric(8,2),
    "price_lifetime" numeric(8,2),
    "is_free" boolean DEFAULT false,
    "strategy_id" "uuid",
    "assets" "text"[],
    "asset_classes" "text"[],
    "tags" "text"[],
    "cem_approved" boolean DEFAULT false,
    "cem_approval_date" timestamp with time zone,
    "cem_vetting_report" "text",
    "cem_backtest_months" integer DEFAULT 6,
    "backtest_win_rate" numeric(5,2),
    "backtest_rr" numeric(5,4),
    "backtest_return_pct" numeric(8,4),
    "backtest_sharpe" numeric(6,4),
    "subscriber_count" integer DEFAULT 0,
    "download_count" integer DEFAULT 0,
    "avg_rating" numeric(3,2) DEFAULT 0,
    "review_count" integer DEFAULT 0,
    "is_featured" boolean DEFAULT false,
    "is_active" boolean DEFAULT true,
    "platform_fee_pct" numeric(4,2) DEFAULT 30.0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_marketplace_listings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_marketplace_purchases" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "buyer_id" "uuid",
    "listing_id" "uuid",
    "purchase_type" "text" DEFAULT 'monthly'::"text",
    "amount_paid" numeric(8,2),
    "seller_revenue" numeric(8,2),
    "platform_revenue" numeric(8,2),
    "stripe_payment_id" "text",
    "active_until" timestamp with time zone,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_marketplace_purchases" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_marketplace_reviews" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "listing_id" "uuid",
    "reviewer_id" "uuid",
    "rating" integer,
    "review_text" "text",
    "verified_purchase" boolean DEFAULT false,
    "helpful_votes" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_marketplace_reviews_rating_check" CHECK ((("rating" >= 1) AND ("rating" <= 5)))
);


ALTER TABLE "public"."cem_marketplace_reviews" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_marketplace_sales" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "strategy_id" "uuid",
    "buyer_id" "uuid",
    "creator_id" "uuid",
    "sale_price" numeric(10,2) NOT NULL,
    "creator_payout" numeric(10,2) GENERATED ALWAYS AS (("sale_price" * 0.30)) STORED,
    "platform_cut" numeric(10,2) GENERATED ALWAYS AS (("sale_price" * 0.70)) STORED,
    "stripe_charge_id" "text",
    "status" "text" DEFAULT 'completed'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_marketplace_sales_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'completed'::"text", 'refunded'::"text"])))
);


ALTER TABLE "public"."cem_marketplace_sales" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_observations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"(),
    "asset_class" "text",
    "symbol" "text",
    "open_price" numeric(18,8),
    "high_price" numeric(18,8),
    "low_price" numeric(18,8),
    "close_price" numeric(18,8),
    "volume" numeric(24,8),
    "regime_classification" "jsonb" DEFAULT '{}'::"jsonb",
    "technical_features" "jsonb" DEFAULT '{}'::"jsonb",
    "correlations" "jsonb" DEFAULT '{}'::"jsonb",
    "feature_vector" "public"."vector"(3072),
    "raw_data_summary" "text",
    "importance_score" integer DEFAULT 5,
    "cycle_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "embedding" "public"."vector"(1536),
    "source" "text",
    "observation" "text",
    "tags" "text"[],
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "compiled_truth" boolean DEFAULT false NOT NULL,
    "compiled_from" "uuid"[],
    "entities" "text"[],
    CONSTRAINT "cem_observations_importance_score_check" CHECK ((("importance_score" >= 1) AND ("importance_score" <= 10)))
);


ALTER TABLE "public"."cem_observations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_ohlc_cache" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "symbol" character varying(20) NOT NULL,
    "interval" character varying(10) NOT NULL,
    "time" bigint NOT NULL,
    "open" numeric,
    "high" numeric,
    "low" numeric,
    "close" numeric,
    "volume" numeric,
    "rsi" numeric,
    "ema9" numeric,
    "ema21" numeric,
    "ema50" numeric,
    "vwap" numeric,
    "bb_upper" numeric,
    "bb_lower" numeric,
    "atr" numeric,
    "fetched_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_ohlc_cache" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_pattern_occurrences" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "symbol" character varying(20),
    "interval" character varying(10),
    "pattern_name" character varying(100),
    "bar_time" bigint,
    "entry_price" numeric,
    "exit_price" numeric,
    "outcome_bars" integer,
    "pnl_pct" numeric,
    "won" boolean,
    "indicator_snapshot" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_pattern_occurrences" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_portfolio" (
    "id" integer NOT NULL,
    "project_title" "text" NOT NULL,
    "category" "text" NOT NULL,
    "period" "text",
    "description" "text",
    "key_contributions" "text"[],
    "skills_demonstrated" "text"[],
    "outcomes" "text",
    "source_project" "text",
    "status" "text" DEFAULT 'active'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_portfolio_status_check" CHECK (("status" = ANY (ARRAY['active'::"text", 'completed'::"text", 'in_progress'::"text", 'archived'::"text"])))
);


ALTER TABLE "public"."cem_portfolio" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_portfolio" IS 'User portfolio tracking — holdings and P&L.';



CREATE SEQUENCE IF NOT EXISTS "public"."cem_portfolio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_portfolio_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_portfolio_id_seq" OWNED BY "public"."cem_portfolio"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_prediction_market_signals" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "platform" "text" NOT NULL,
    "market_id" "text",
    "market_question" "text" NOT NULL,
    "market_category" "text",
    "kalshi_yes_price" numeric,
    "kalshi_no_price" numeric,
    "polymarket_yes_price" numeric,
    "polymarket_no_price" numeric,
    "divergence_pct" numeric,
    "divergence_direction" "text",
    "signal_strength" "text",
    "related_asset" "text",
    "suggested_trade" "text",
    "trade_rationale" "text",
    "paper_entry_price" numeric,
    "paper_current_price" numeric,
    "paper_pnl" numeric DEFAULT 0,
    "paper_pnl_pct" numeric DEFAULT 0,
    "trade_direction" "text",
    "trade_status" "text" DEFAULT 'watching'::"text",
    "trade_opened_at" timestamp with time zone,
    "trade_closed_at" timestamp with time zone,
    "resolved" boolean DEFAULT false,
    "resolution" "text",
    "resolved_at" timestamp with time zone,
    "was_correct" boolean,
    "notes" "text"
);


ALTER TABLE "public"."cem_prediction_market_signals" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_session_files" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "account_id" "uuid",
    "strategy_id" "uuid",
    "session_number" integer,
    "session_type" "text" DEFAULT 'backtest'::"text",
    "asset" "text",
    "timeframe" "text",
    "date_from" "date",
    "date_to" "date",
    "bars_count" integer,
    "net_pnl" numeric(12,2),
    "win_rate" numeric(5,4),
    "total_trades" integer,
    "avg_rr" numeric(6,4),
    "profit_factor" numeric(6,4),
    "max_drawdown" numeric(12,2),
    "sharpe_ratio" numeric(6,4),
    "avg_hold_hours" numeric(8,4),
    "strategy_params" "jsonb",
    "trades" "jsonb" DEFAULT '[]'::"jsonb",
    "cem_notes" "jsonb" DEFAULT '[]'::"jsonb",
    "journal_entries" "jsonb" DEFAULT '[]'::"jsonb",
    "market_conditions" "jsonb",
    "strategy_score_start" integer,
    "strategy_score_end" integer,
    "previous_session_id" "uuid",
    "cem_coaching_report" "text",
    "cem_rating" "text",
    "cem_angles" "jsonb" DEFAULT '[]'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_session_files" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_session_log" (
    "id" integer NOT NULL,
    "session_date" "date" DEFAULT CURRENT_DATE NOT NULL,
    "summary" "text" NOT NULL,
    "decisions_changed" "text"[],
    "bugs_fixed" "text"[],
    "bugs_remaining" "text"[],
    "next_priorities" "text"[],
    "written_by" "text" DEFAULT 'Clyde'::"text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_session_log" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_session_log_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_session_log_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_session_log_id_seq" OWNED BY "public"."cem_session_log"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "session_id" "text" NOT NULL,
    "user_id" "text" NOT NULL,
    "started_at" timestamp without time zone DEFAULT "now"(),
    "ended_at" timestamp without time zone,
    "total_runs" integer DEFAULT 0,
    "best_score" double precision DEFAULT 0,
    "best_return" double precision DEFAULT 0,
    "best_params" "jsonb",
    "session_summary" "text",
    "improvement_delta" double precision DEFAULT 0
);


ALTER TABLE "public"."cem_sessions" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_sessions" IS 'User session tracking — login events and activity.';



CREATE TABLE IF NOT EXISTS "public"."cem_ship_log" (
    "id" integer NOT NULL,
    "logged_at" timestamp with time zone DEFAULT "now"(),
    "date" "text" NOT NULL,
    "what_shipped" "text" NOT NULL,
    "file_changed" "text",
    "verified" boolean DEFAULT false,
    "md5_after" "text",
    "bytes_after" integer,
    "notes" "text",
    "status" "text" DEFAULT 'SHIPPED'::"text",
    "logged_by" "text" DEFAULT 'clyde'::"text",
    "session_start" boolean DEFAULT false,
    "session_end" boolean DEFAULT false,
    "brain_keys_written" "text",
    "supabase_tables_touched" "text",
    CONSTRAINT "cem_ship_log_status_check" CHECK (("status" = ANY (ARRAY['SHIPPED'::"text", 'FAILED'::"text", 'PENDING'::"text", 'ROLLED_BACK'::"text"])))
);


ALTER TABLE "public"."cem_ship_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_ship_log" IS 'Permanent record of every deploy, change, and verified action. Every Claude writes here when something ships. This is the source of truth.';



COMMENT ON COLUMN "public"."cem_ship_log"."verified" IS 'TRUE only when Claude has actual server proof: md5sum, row count, HTTP check. Never set true on assumption.';



COMMENT ON COLUMN "public"."cem_ship_log"."session_start" IS 'TRUE on the first row Claude writes when opening a session — CHECK IN';



COMMENT ON COLUMN "public"."cem_ship_log"."session_end" IS 'TRUE on the last row Claude writes before ending a session — CHECK OUT';



COMMENT ON COLUMN "public"."cem_ship_log"."brain_keys_written" IS 'Comma-separated list of every brain key written this action';



COMMENT ON COLUMN "public"."cem_ship_log"."supabase_tables_touched" IS 'Comma-separated list of every Supabase table touched this action';



CREATE SEQUENCE IF NOT EXISTS "public"."cem_ship_log_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_ship_log_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_ship_log_id_seq" OWNED BY "public"."cem_ship_log"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_smart_alerts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "alert_name" "text" NOT NULL,
    "asset" "text" NOT NULL,
    "alert_type" "text" DEFAULT 'indicator'::"text",
    "conditions" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "notification_methods" "text"[] DEFAULT '{telegram}'::"text"[],
    "cem_voice_note" boolean DEFAULT true,
    "is_active" boolean DEFAULT true,
    "last_triggered" timestamp with time zone,
    "trigger_count" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_smart_alerts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_strategies" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "strategy_type" "text",
    "asset_class" "text",
    "timeframe" "text" NOT NULL,
    "parameters" "jsonb" DEFAULT '{}'::"jsonb",
    "sharpe_ratio" numeric(8,4),
    "sortino_ratio" numeric(8,4),
    "calmar_ratio" numeric(8,4),
    "max_drawdown" numeric(8,4),
    "volatility" numeric(8,4),
    "win_rate" numeric(5,2),
    "avg_return" numeric(8,4),
    "total_return" numeric(12,4),
    "risk_profile" "jsonb" DEFAULT '{"max_leverage": 1.0, "volatility_regime": "medium"}'::"jsonb",
    "turnover" numeric(8,4),
    "holding_period_avg" interval,
    "trades_per_day" numeric(6,2),
    "optimal_regimes" "jsonb" DEFAULT '[]'::"jsonb",
    "regime_tags" "text"[] DEFAULT '{}'::"text"[],
    "lineage_parent_id" "uuid",
    "lineage_generation" integer DEFAULT 0,
    "mutation_type" "text",
    "fingerprint_vector" "public"."vector"(3072),
    "parameter_hash" "text",
    "validation_status" "text" DEFAULT 'unvalidated'::"text",
    "paper_trading_start" timestamp with time zone,
    "paper_trading_end" timestamp with time zone,
    "paper_trading_sharpe" numeric(8,4),
    "live_deployed_at" timestamp with time zone,
    "live_performance" "jsonb" DEFAULT '{}'::"jsonb",
    "importance_score" integer DEFAULT 5,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "last_evaluated" timestamp with time zone,
    "last_accessed" timestamp with time zone DEFAULT "now"(),
    "embedding" "public"."vector"(1536),
    "asset" "text",
    "market_condition" "text",
    "tier" "text" DEFAULT 'verified'::"text",
    "fts" "tsvector",
    CONSTRAINT "cem_strategies_asset_class_check" CHECK (("asset_class" = ANY (ARRAY['crypto'::"text", 'micro_futures'::"text", 'regular_futures'::"text", 'forex'::"text", 'stocks'::"text", 'prediction_markets'::"text"]))),
    CONSTRAINT "cem_strategies_importance_score_check" CHECK ((("importance_score" >= 1) AND ("importance_score" <= 10))),
    CONSTRAINT "cem_strategies_mutation_type_check" CHECK (("mutation_type" = ANY (ARRAY['parameter'::"text", 'structural'::"text", 'crossover'::"text", 'initial'::"text"]))),
    CONSTRAINT "cem_strategies_strategy_type_check" CHECK (("strategy_type" = ANY (ARRAY['momentum'::"text", 'mean_reversion'::"text", 'statistical_arbitrage'::"text", 'breakout'::"text", 'trend_following'::"text"]))),
    CONSTRAINT "cem_strategies_validation_status_check" CHECK (("validation_status" = ANY (ARRAY['unvalidated'::"text", 'walk_forward_passed'::"text", 'monte_carlo_passed'::"text", 'live_deployed'::"text", 'deprecated'::"text"])))
);


ALTER TABLE "public"."cem_strategies" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_strategy_blocks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "strategy_id" "uuid",
    "block_type" "text" NOT NULL,
    "sort_order" integer DEFAULT 0 NOT NULL,
    "indicator" "text",
    "operator" "text",
    "value_type" "text",
    "value_a" "jsonb",
    "value_b" "jsonb",
    "action" "text",
    "action_params" "jsonb" DEFAULT '{}'::"jsonb",
    "label" "text",
    "cem_explanation" "text",
    "is_enabled" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_strategy_blocks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_strategy_combos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "strategy_a" "text" NOT NULL,
    "strategy_b" "text" NOT NULL,
    "asset" "text" NOT NULL,
    "timeframe" "text" DEFAULT '15m'::"text",
    "combo_win_rate" numeric,
    "combo_profit_factor" numeric,
    "solo_a_win_rate" numeric,
    "solo_b_win_rate" numeric,
    "improvement_over_best" numeric,
    "total_trades" integer,
    "regime" "text",
    "verdict" "text",
    "notes" "text",
    "layers" integer DEFAULT 2
);


ALTER TABLE "public"."cem_strategy_combos" OWNER TO "postgres";


COMMENT ON COLUMN "public"."cem_strategy_combos"."strategy_b" IS 'Indicator combination as "+" separated string e.g. EMA+RSI+VWAP for 3-layer combo';



COMMENT ON COLUMN "public"."cem_strategy_combos"."layers" IS 'How many indicator layers in this combo — 2, 3, 4, or 5';



CREATE TABLE IF NOT EXISTS "public"."cem_strategy_library" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "is_anonymous" boolean DEFAULT false,
    "name" "text",
    "asset" "text" NOT NULL,
    "timeframe" "text" NOT NULL,
    "signals" "jsonb" NOT NULL,
    "filters" "jsonb",
    "risk_settings" "jsonb",
    "session_settings" "jsonb",
    "best_backtest" "jsonb",
    "market_condition" "text",
    "tier" "text" DEFAULT 'open'::"text",
    "is_marketplace" boolean DEFAULT false,
    "price_usd" numeric(10,2),
    "embedding" "public"."vector"(1536),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "fts" "tsvector",
    CONSTRAINT "cem_strategy_library_market_condition_check" CHECK (("market_condition" = ANY (ARRAY['trending'::"text", 'ranging'::"text", 'volatile'::"text", 'any'::"text"]))),
    CONSTRAINT "cem_strategy_library_tier_check" CHECK (("tier" = ANY (ARRAY['open'::"text", 'verified'::"text", 'live_tested'::"text", 'elite'::"text"])))
);


ALTER TABLE "public"."cem_strategy_library" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_strategy_optimization" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "base_strategy" "text" NOT NULL,
    "asset" "text" NOT NULL,
    "variant_params" "jsonb" NOT NULL,
    "win_rate" numeric,
    "profit_factor" numeric,
    "total_trades" integer,
    "sharpe" numeric,
    "improvement_pct" numeric,
    "is_best_variant" boolean DEFAULT false,
    "notes" "text"
);


ALTER TABLE "public"."cem_strategy_optimization" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_thresholds" (
    "id" integer NOT NULL,
    "name" "text" NOT NULL,
    "value" numeric NOT NULL,
    "description" "text",
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_thresholds" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_thresholds_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_thresholds_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_thresholds_id_seq" OWNED BY "public"."cem_thresholds"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_todo" (
    "id" integer NOT NULL,
    "priority" integer NOT NULL,
    "category" "text",
    "title" "text" NOT NULL,
    "description" "text",
    "status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "completed_at" timestamp with time zone
);


ALTER TABLE "public"."cem_todo" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cem_todo_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cem_todo_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cem_todo_id_seq" OWNED BY "public"."cem_todo"."id";



CREATE TABLE IF NOT EXISTS "public"."cem_trade_copies" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "original_trade_id" "uuid",
    "original_user_id" "uuid",
    "copying_user_id" "uuid",
    "copying_account_id" "uuid",
    "scale_factor" numeric(5,4) DEFAULT 1.0,
    "status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_trade_copies" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_trading_accounts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "name" "text" NOT NULL,
    "account_type" "text" DEFAULT 'paper'::"text" NOT NULL,
    "starting_balance" numeric(12,2) DEFAULT 10000 NOT NULL,
    "current_balance" numeric(12,2) DEFAULT 10000 NOT NULL,
    "strategy_pnl" numeric(12,2) DEFAULT 0 NOT NULL,
    "manual_pnl" numeric(12,2) DEFAULT 0 NOT NULL,
    "total_pnl" numeric(12,2) GENERATED ALWAYS AS (("strategy_pnl" + "manual_pnl")) STORED,
    "return_pct" numeric(8,4) GENERATED ALWAYS AS (
CASE
    WHEN ("starting_balance" > (0)::numeric) THEN ((("strategy_pnl" + "manual_pnl") / "starting_balance") * (100)::numeric)
    ELSE (0)::numeric
END) STORED,
    "assets" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "asset_classes" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "prop_firm" "text",
    "prop_rules" "jsonb" DEFAULT '{}'::"jsonb",
    "strategy_id" "uuid",
    "strategy_name" "text",
    "is_active" boolean DEFAULT true NOT NULL,
    "is_master" boolean DEFAULT false NOT NULL,
    "is_public" boolean DEFAULT false NOT NULL,
    "cem_notes" "text",
    "equity_curve" "jsonb" DEFAULT '[]'::"jsonb",
    "stats" "jsonb" DEFAULT '{}'::"jsonb",
    "color" "text" DEFAULT '#00C4B3'::"text",
    "session_count" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_trading_accounts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_user_library_progress" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "lesson_id" integer,
    "snapshots_viewed" integer DEFAULT 0,
    "quiz_score" numeric,
    "last_viewed_at" timestamp with time zone,
    "completed" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_user_library_progress" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_user_memory" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "text" NOT NULL,
    "memory_type" "text" NOT NULL,
    "content" "text" NOT NULL,
    "embedding" "public"."vector"(1536),
    "importance_score" double precision DEFAULT 0.5,
    "confirmation_count" integer DEFAULT 1,
    "source_session_id" "text",
    "asset_class" "text",
    "market_regime" "text",
    "created_at" timestamp without time zone DEFAULT "now"(),
    "last_confirmed_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_user_memory" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_user_memory" IS 'Per-user AI memory — what CEMbot has learned about each trader.';



CREATE TABLE IF NOT EXISTS "public"."cem_user_profiles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "text" NOT NULL,
    "archetype" "text" DEFAULT 'unknown'::"text",
    "risk_tolerance" double precision DEFAULT 0.5,
    "favorite_asset" "text",
    "total_sessions" integer DEFAULT 0,
    "total_backtests" integer DEFAULT 0,
    "average_strategy_score" double precision DEFAULT 0,
    "improvement_velocity" double precision DEFAULT 0,
    "xp_points" integer DEFAULT 0,
    "cembot_voice_mode" "text" DEFAULT 'explorer'::"text",
    "created_at" timestamp without time zone DEFAULT "now"(),
    "last_active" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_user_profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_user_profiles" IS 'Extended user profile data — trading style, experience level, preferences.';



CREATE TABLE IF NOT EXISTS "public"."cem_user_uploads" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "file_name" "text",
    "file_type" "text",
    "source_platform" "text",
    "parsed_data" "jsonb",
    "style_detected" "text",
    "cem_analysis" "text",
    "strategy_built" "uuid",
    "upload_date" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "cem_user_uploads_file_type_check" CHECK (("file_type" = ANY (ARRAY['csv'::"text", 'pdf'::"text", 'xlsx'::"text", 'screenshot'::"text", 'json'::"text"])))
);


ALTER TABLE "public"."cem_user_uploads" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."cem_users" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "username" "text" NOT NULL,
    "display_name" "text" NOT NULL,
    "role" "text" NOT NULL,
    "pin_hash" "text" NOT NULL,
    "preferences" "jsonb" DEFAULT '{}'::"jsonb",
    "active_tasks" "jsonb" DEFAULT '[]'::"jsonb",
    "context_notes" "text" DEFAULT ''::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "date_of_birth" "date",
    "show_age" boolean DEFAULT false,
    "tier" "text" DEFAULT 'free'::"text",
    "invite_code" "text",
    "beta_access" boolean DEFAULT false,
    "is_admin" boolean DEFAULT false,
    "invited_by_code" "text",
    "subscription_source" "text" DEFAULT 'organic'::"text"
);


ALTER TABLE "public"."cem_users" OWNER TO "postgres";


COMMENT ON TABLE "public"."cem_users" IS 'Platform users — created when someone signs up or purchases.';



CREATE TABLE IF NOT EXISTS "public"."cem_weather_trades" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "hetzner_id" integer,
    "market_ticker" "text",
    "market_title" "text",
    "platform" "text",
    "category" "text",
    "direction" "text",
    "entry_price" double precision,
    "exit_price" double precision,
    "size" double precision,
    "pnl" double precision,
    "status" "text" DEFAULT 'open'::"text",
    "result" "text",
    "edge_at_entry" double precision,
    "model_probability" double precision,
    "market_probability" double precision,
    "is_arb" boolean DEFAULT false,
    "arb_counterpart_ticker" "text",
    "reasoning" "text",
    "simulation_mode" boolean DEFAULT true,
    "opened_at" timestamp with time zone DEFAULT "now"(),
    "settled_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."cem_weather_trades" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."cem_weather_bot_performance" AS
 SELECT "category",
    "platform",
    "count"(*) AS "total_trades",
    "sum"(
        CASE
            WHEN ("result" = 'win'::"text") THEN 1
            ELSE 0
        END) AS "wins",
    "round"(((("sum"(
        CASE
            WHEN ("result" = 'win'::"text") THEN 1
            ELSE 0
        END))::numeric / (NULLIF("count"(*), 0))::numeric) * (100)::numeric), 1) AS "win_rate_pct",
    "round"(("sum"("pnl"))::numeric, 2) AS "total_pnl",
    "round"(("avg"("edge_at_entry"))::numeric, 3) AS "avg_edge",
    "max"("settled_at") AS "last_trade"
   FROM "public"."cem_weather_trades"
  WHERE ("status" = 'closed'::"text")
  GROUP BY "category", "platform"
  ORDER BY ("round"(("sum"("pnl"))::numeric, 2)) DESC;


ALTER VIEW "public"."cem_weather_bot_performance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."conversation_messages" (
    "id" character varying NOT NULL,
    "conversation_id" character varying,
    "agent_id" character varying NOT NULL,
    "message_id" character varying NOT NULL,
    "position" integer NOT NULL,
    "in_context" boolean NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."conversation_messages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."conversations" (
    "id" character varying NOT NULL,
    "agent_id" character varying NOT NULL,
    "summary" character varying,
    "model" character varying,
    "model_settings" json,
    "last_message_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."conversations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."file_contents" (
    "id" character varying NOT NULL,
    "file_id" character varying NOT NULL,
    "text" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."file_contents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."files" (
    "file_name" character varying,
    "original_file_name" character varying,
    "file_path" character varying,
    "file_type" character varying,
    "file_size" integer,
    "file_creation_date" character varying,
    "file_last_modified_date" character varying,
    "processing_status" character varying NOT NULL,
    "error_message" "text",
    "total_chunks" integer,
    "chunks_embedded" integer,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "source_id" character varying NOT NULL
);


ALTER TABLE "public"."files" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."files_agents" (
    "id" character varying NOT NULL,
    "file_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL,
    "source_id" character varying NOT NULL,
    "file_name" character varying NOT NULL,
    "is_open" boolean NOT NULL,
    "visible_content" "text",
    "last_accessed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "start_line" integer,
    "end_line" integer,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."files_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."groups" (
    "id" character varying NOT NULL,
    "description" character varying NOT NULL,
    "manager_type" character varying NOT NULL,
    "manager_agent_id" character varying,
    "termination_token" character varying,
    "max_turns" integer,
    "sleeptime_agent_frequency" integer,
    "max_message_buffer_length" integer,
    "min_message_buffer_length" integer,
    "turns_counter" integer,
    "last_processed_message_id" character varying,
    "hidden" boolean,
    "agent_ids" json NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "project_id" character varying,
    "base_template_id" character varying,
    "template_id" character varying,
    "deployment_id" character varying
);


ALTER TABLE "public"."groups" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."groups_agents" (
    "group_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."groups_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."groups_blocks" (
    "group_id" character varying NOT NULL,
    "block_id" character varying NOT NULL
);


ALTER TABLE "public"."groups_blocks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."identities" (
    "id" character varying NOT NULL,
    "identifier_key" character varying NOT NULL,
    "name" character varying NOT NULL,
    "identity_type" character varying NOT NULL,
    "properties" json NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "project_id" character varying
);


ALTER TABLE "public"."identities" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."identities_agents" (
    "identity_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."identities_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."identities_blocks" (
    "identity_id" character varying NOT NULL,
    "block_id" character varying NOT NULL
);


ALTER TABLE "public"."identities_blocks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."jobs" (
    "status" character varying NOT NULL,
    "completed_at" timestamp without time zone,
    "stop_reason" character varying,
    "background" boolean,
    "metadata_" json,
    "job_type" character varying NOT NULL,
    "request_config" json,
    "organization_id" character varying,
    "callback_url" character varying,
    "callback_sent_at" timestamp without time zone,
    "callback_status_code" integer,
    "callback_error" character varying,
    "ttft_ns" bigint,
    "total_duration_ns" bigint,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "user_id" character varying NOT NULL
);


ALTER TABLE "public"."jobs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."llm_batch_items" (
    "id" character varying NOT NULL,
    "llm_batch_id" character varying NOT NULL,
    "llm_config" json NOT NULL,
    "request_status" character varying NOT NULL,
    "step_status" character varying NOT NULL,
    "step_state" json NOT NULL,
    "batch_request_result" json,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."llm_batch_items" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."llm_batch_job" (
    "id" character varying NOT NULL,
    "status" character varying NOT NULL,
    "llm_provider" character varying NOT NULL,
    "create_batch_response" json NOT NULL,
    "latest_polling_response" json,
    "last_polled_at" timestamp with time zone,
    "letta_batch_job_id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."llm_batch_job" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."mcp_oauth" (
    "id" character varying NOT NULL,
    "state" character varying(255) NOT NULL,
    "server_id" character varying(255),
    "server_url" "text" NOT NULL,
    "server_name" "text" NOT NULL,
    "authorization_url" "text",
    "authorization_code" "text",
    "authorization_code_enc" "text",
    "access_token" "text",
    "access_token_enc" "text",
    "refresh_token" "text",
    "refresh_token_enc" "text",
    "token_type" character varying(50) NOT NULL,
    "expires_at" timestamp with time zone,
    "scope" "text",
    "client_id" "text",
    "client_secret" "text",
    "client_secret_enc" "text",
    "redirect_uri" "text",
    "status" character varying(20) NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "user_id" character varying NOT NULL
);


ALTER TABLE "public"."mcp_oauth" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."mcp_server" (
    "server_name" character varying NOT NULL,
    "server_type" character varying NOT NULL,
    "server_url" character varying,
    "token" character varying,
    "token_enc" "text",
    "custom_headers" json,
    "custom_headers_enc" "text",
    "stdio_config" json,
    "metadata_" json,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."mcp_server" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."mcp_tools" (
    "mcp_server_id" character varying NOT NULL,
    "tool_id" character varying NOT NULL,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."mcp_tools" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."messages_sequence_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."messages_sequence_id_seq" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."messages" (
    "id" character varying NOT NULL,
    "role" character varying NOT NULL,
    "text" character varying,
    "content" json,
    "model" character varying,
    "name" character varying,
    "tool_calls" json NOT NULL,
    "tool_call_id" character varying,
    "step_id" character varying,
    "run_id" character varying,
    "otid" character varying,
    "tool_returns" json,
    "group_id" character varying,
    "sender_id" character varying,
    "batch_item_id" character varying,
    "conversation_id" character varying,
    "is_err" boolean,
    "approval_request_id" character varying,
    "approve" boolean,
    "denial_reason" character varying,
    "approvals" json,
    "sequence_id" bigint DEFAULT "nextval"('"public"."messages_sequence_id_seq"'::"regclass") NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."messages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."orders" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "stripe_session_id" "text",
    "stripe_payment_intent_id" "text",
    "tier" "text" NOT NULL,
    "amount_total" integer,
    "currency" "text" DEFAULT 'usd'::"text",
    "status" "text" DEFAULT 'pending'::"text",
    "customer_email" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."orders" OWNER TO "postgres";


COMMENT ON TABLE "public"."orders" IS 'Purchase orders — bot purchases and subscription events. Wires to Stripe.';



CREATE TABLE IF NOT EXISTS "public"."organizations" (
    "name" character varying NOT NULL,
    "privileged_tools" boolean NOT NULL,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."organizations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."passage_tags" (
    "id" character varying NOT NULL,
    "tag" character varying NOT NULL,
    "passage_id" character varying NOT NULL,
    "archive_id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."passage_tags" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."prompts" (
    "id" character varying NOT NULL,
    "prompt" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "project_id" character varying
);


ALTER TABLE "public"."prompts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."provider_models" (
    "handle" character varying NOT NULL,
    "display_name" character varying NOT NULL,
    "name" character varying NOT NULL,
    "provider_id" character varying NOT NULL,
    "organization_id" character varying,
    "model_type" character varying NOT NULL,
    "enabled" boolean DEFAULT true NOT NULL,
    "model_endpoint_type" character varying NOT NULL,
    "max_context_window" integer,
    "supports_token_streaming" boolean,
    "supports_tool_calling" boolean,
    "embedding_dim" integer,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."provider_models" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."provider_trace_metadata" (
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "id" character varying NOT NULL,
    "step_id" character varying,
    "agent_id" character varying,
    "agent_tags" json,
    "call_type" character varying,
    "run_id" character varying,
    "source" character varying,
    "org_id" character varying,
    "user_id" character varying,
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."provider_trace_metadata" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."provider_traces" (
    "id" character varying NOT NULL,
    "request_json" json NOT NULL,
    "response_json" json NOT NULL,
    "step_id" character varying,
    "agent_id" character varying,
    "agent_tags" json,
    "call_type" character varying,
    "run_id" character varying,
    "source" character varying,
    "org_id" character varying,
    "user_id" character varying,
    "compaction_settings" json,
    "llm_config" json,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."provider_traces" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."providers" (
    "organization_id" character varying,
    "name" character varying NOT NULL,
    "provider_type" character varying,
    "provider_category" character varying,
    "api_key" character varying,
    "base_url" character varying,
    "access_key" character varying,
    "region" character varying,
    "api_version" character varying,
    "api_key_enc" "text",
    "access_key_enc" "text",
    "last_synced" timestamp with time zone,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying
);


ALTER TABLE "public"."providers" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."run_metrics" (
    "id" character varying NOT NULL,
    "run_start_ns" bigint,
    "run_ns" bigint,
    "num_steps" integer,
    "tools_used" json,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "project_id" character varying,
    "agent_id" character varying NOT NULL,
    "organization_id" character varying NOT NULL,
    "base_template_id" character varying,
    "template_id" character varying,
    "deployment_id" character varying
);


ALTER TABLE "public"."run_metrics" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."runs" (
    "id" character varying NOT NULL,
    "status" character varying NOT NULL,
    "completed_at" timestamp without time zone,
    "stop_reason" character varying,
    "background" boolean,
    "metadata_" json,
    "request_config" json,
    "agent_id" character varying NOT NULL,
    "conversation_id" character varying,
    "callback_url" character varying,
    "callback_sent_at" timestamp without time zone,
    "callback_status_code" integer,
    "callback_error" character varying,
    "ttft_ns" bigint,
    "total_duration_ns" bigint,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "project_id" character varying,
    "base_template_id" character varying,
    "template_id" character varying,
    "deployment_id" character varying
);


ALTER TABLE "public"."runs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."sandbox_configs" (
    "id" character varying NOT NULL,
    "type" "public"."sandboxtype" NOT NULL,
    "config" json NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."sandbox_configs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."sandbox_environment_variables" (
    "id" character varying NOT NULL,
    "key" character varying NOT NULL,
    "value" character varying NOT NULL,
    "description" character varying,
    "value_enc" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "sandbox_config_id" character varying NOT NULL
);


ALTER TABLE "public"."sandbox_environment_variables" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."source_passages" (
    "file_name" character varying NOT NULL,
    "id" character varying NOT NULL,
    "text" character varying NOT NULL,
    "embedding_config" json,
    "metadata_" json NOT NULL,
    "tags" json,
    "embedding" "public"."vector"(4096),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "file_id" character varying,
    "source_id" character varying NOT NULL
);


ALTER TABLE "public"."source_passages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."sources" (
    "name" character varying NOT NULL,
    "description" character varying,
    "instructions" character varying,
    "embedding_config" json NOT NULL,
    "metadata_" json,
    "vector_db_provider" "public"."vectordbprovider" NOT NULL,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."sources" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."sources_agents" (
    "agent_id" character varying NOT NULL,
    "source_id" character varying NOT NULL
);


ALTER TABLE "public"."sources_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."step_metrics" (
    "id" character varying NOT NULL,
    "organization_id" character varying,
    "provider_id" character varying,
    "run_id" character varying,
    "step_start_ns" bigint,
    "llm_request_start_ns" bigint,
    "llm_request_ns" bigint,
    "tool_execution_ns" bigint,
    "step_ns" bigint,
    "base_template_id" character varying,
    "template_id" character varying,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "project_id" character varying,
    "agent_id" character varying NOT NULL
);


ALTER TABLE "public"."step_metrics" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."steps" (
    "id" character varying NOT NULL,
    "origin" character varying,
    "organization_id" character varying,
    "provider_id" character varying,
    "run_id" character varying,
    "agent_id" character varying,
    "provider_name" character varying,
    "provider_category" character varying,
    "model" character varying,
    "model_handle" character varying,
    "model_endpoint" character varying,
    "context_window_limit" integer,
    "completion_tokens" integer NOT NULL,
    "prompt_tokens" integer NOT NULL,
    "total_tokens" integer NOT NULL,
    "cached_input_tokens" integer,
    "cache_write_tokens" integer,
    "reasoning_tokens" integer,
    "completion_tokens_details" json,
    "prompt_tokens_details" json,
    "stop_reason" character varying,
    "tags" json,
    "tid" character varying,
    "trace_id" character varying,
    "request_id" character varying,
    "feedback" character varying,
    "error_type" character varying,
    "error_data" json,
    "status" "public"."stepstatus",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "project_id" character varying
);


ALTER TABLE "public"."steps" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tools" (
    "name" character varying NOT NULL,
    "tool_type" character varying NOT NULL,
    "return_char_limit" integer,
    "description" character varying,
    "tags" json NOT NULL,
    "source_type" character varying NOT NULL,
    "source_code" character varying,
    "json_schema" json,
    "args_json_schema" json,
    "pip_requirements" json,
    "npm_requirements" json,
    "default_requires_approval" boolean,
    "enable_parallel_execution" boolean,
    "metadata_" json,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL,
    "project_id" character varying
);


ALTER TABLE "public"."tools" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tools_agents" (
    "agent_id" character varying NOT NULL,
    "tool_id" character varying NOT NULL
);


ALTER TABLE "public"."tools_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."users" (
    "name" character varying NOT NULL,
    "id" character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "is_deleted" boolean DEFAULT false NOT NULL,
    "_created_by_id" character varying,
    "_last_updated_by_id" character varying,
    "organization_id" character varying NOT NULL
);


ALTER TABLE "public"."users" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."v_strategy_portfolio" AS
 SELECT "id",
    "name",
    "strategy_type",
    "asset_class",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "validation_status",
    "live_deployed_at",
    "importance_score",
    "created_at",
        CASE
            WHEN ("live_deployed_at" IS NOT NULL) THEN 'LIVE'::"text"
            WHEN ("paper_trading_end" IS NOT NULL) THEN 'PAPER'::"text"
            ELSE 'BACKTEST'::"text"
        END AS "deployment_stage"
   FROM "public"."cem_strategies" "s"
  WHERE ("validation_status" = ANY (ARRAY['walk_forward_passed'::"text", 'monte_carlo_passed'::"text", 'live_deployed'::"text"]))
  ORDER BY "sharpe_ratio" DESC NULLS LAST;


ALTER VIEW "public"."v_strategy_portfolio" OWNER TO "postgres";


ALTER TABLE ONLY "public"."cem_decisions" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_decisions_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_eureka_journal" ALTER COLUMN "journal_number" SET DEFAULT "nextval"('"public"."cem_eureka_journal_journal_number_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_github_staging" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_github_staging_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_known_fixes" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_known_fixes_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_library_lessons" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_library_lessons_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_portfolio" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_portfolio_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_session_log" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_session_log_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_ship_log" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_ship_log_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_thresholds" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_thresholds_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cem_todo" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cem_todo_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."agent_environment_variables"
    ADD CONSTRAINT "agent_environment_variables_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."agents"
    ADD CONSTRAINT "agents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."archival_passages"
    ADD CONSTRAINT "archival_passages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."archives_agents"
    ADD CONSTRAINT "archives_agents_pkey" PRIMARY KEY ("agent_id", "archive_id");



ALTER TABLE ONLY "public"."archives"
    ADD CONSTRAINT "archives_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."block_history"
    ADD CONSTRAINT "block_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."block"
    ADD CONSTRAINT "block_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."blocks_agents"
    ADD CONSTRAINT "blocks_agents_pkey" PRIMARY KEY ("agent_id", "block_id", "block_label");



ALTER TABLE ONLY "public"."blocks_conversations"
    ADD CONSTRAINT "blocks_conversations_pkey" PRIMARY KEY ("conversation_id", "block_id", "block_label");



ALTER TABLE ONLY "public"."bot_delivery_jobs"
    ADD CONSTRAINT "bot_delivery_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_account_trades"
    ADD CONSTRAINT "cem_account_trades_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_beta_invites"
    ADD CONSTRAINT "cem_beta_invites_code_key" UNIQUE ("code");



ALTER TABLE ONLY "public"."cem_beta_invites"
    ADD CONSTRAINT "cem_beta_invites_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_bot_heartbeats"
    ADD CONSTRAINT "cem_bot_heartbeats_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_bot_performance"
    ADD CONSTRAINT "cem_bot_performance_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_bots"
    ADD CONSTRAINT "cem_bots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_coach_research"
    ADD CONSTRAINT "cem_coach_research_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_community_follows"
    ADD CONSTRAINT "cem_community_follows_follower_id_following_id_key" UNIQUE ("follower_id", "following_id");



ALTER TABLE ONLY "public"."cem_community_follows"
    ADD CONSTRAINT "cem_community_follows_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_community_insights"
    ADD CONSTRAINT "cem_community_insights_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_community_posts"
    ADD CONSTRAINT "cem_community_posts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_congress_live"
    ADD CONSTRAINT "cem_congress_live_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_context"
    ADD CONSTRAINT "cem_context_key_key" UNIQUE ("key");



ALTER TABLE ONLY "public"."cem_context"
    ADD CONSTRAINT "cem_context_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_conversations"
    ADD CONSTRAINT "cem_conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_curriculum_connections"
    ADD CONSTRAINT "cem_curriculum_connections_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_curriculum_instances"
    ADD CONSTRAINT "cem_curriculum_instances_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_curriculum_nodes"
    ADD CONSTRAINT "cem_curriculum_nodes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_decisions"
    ADD CONSTRAINT "cem_decisions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_embedding_queue"
    ADD CONSTRAINT "cem_embedding_queue_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_embedding_queue"
    ADD CONSTRAINT "cem_embedding_queue_source_table_source_id_key" UNIQUE ("source_table", "source_id");



ALTER TABLE ONLY "public"."cem_episodes"
    ADD CONSTRAINT "cem_episodes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_eureka_journal"
    ADD CONSTRAINT "cem_eureka_journal_local_id_key" UNIQUE ("local_id");



ALTER TABLE ONLY "public"."cem_eureka_journal"
    ADD CONSTRAINT "cem_eureka_journal_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_github_staging"
    ADD CONSTRAINT "cem_github_staging_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_indicator_isolation"
    ADD CONSTRAINT "cem_indicator_isolation_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_insight_notes"
    ADD CONSTRAINT "cem_insight_notes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_insights"
    ADD CONSTRAINT "cem_insights_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_invite_codes"
    ADD CONSTRAINT "cem_invite_codes_code_key" UNIQUE ("code");



ALTER TABLE ONLY "public"."cem_invite_codes"
    ADD CONSTRAINT "cem_invite_codes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_knowledge_embeddings"
    ADD CONSTRAINT "cem_knowledge_embeddings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_known_fixes"
    ADD CONSTRAINT "cem_known_fixes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_library_lessons"
    ADD CONSTRAINT "cem_library_lessons_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_links"
    ADD CONSTRAINT "cem_links_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_live_trades"
    ADD CONSTRAINT "cem_live_trades_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_market_snapshots"
    ADD CONSTRAINT "cem_market_snapshots_asset_snapshot_date_key" UNIQUE ("asset", "snapshot_date");



ALTER TABLE ONLY "public"."cem_market_snapshots"
    ADD CONSTRAINT "cem_market_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_marketplace_listings"
    ADD CONSTRAINT "cem_marketplace_listings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_marketplace_purchases"
    ADD CONSTRAINT "cem_marketplace_purchases_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_marketplace_reviews"
    ADD CONSTRAINT "cem_marketplace_reviews_listing_id_reviewer_id_key" UNIQUE ("listing_id", "reviewer_id");



ALTER TABLE ONLY "public"."cem_marketplace_reviews"
    ADD CONSTRAINT "cem_marketplace_reviews_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_marketplace_sales"
    ADD CONSTRAINT "cem_marketplace_sales_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_observations"
    ADD CONSTRAINT "cem_observations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_ohlc_cache"
    ADD CONSTRAINT "cem_ohlc_cache_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_ohlc_cache"
    ADD CONSTRAINT "cem_ohlc_cache_symbol_interval_time_key" UNIQUE ("symbol", "interval", "time");



ALTER TABLE ONLY "public"."cem_pattern_occurrences"
    ADD CONSTRAINT "cem_pattern_occurrences_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_portfolio"
    ADD CONSTRAINT "cem_portfolio_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_prediction_market_signals"
    ADD CONSTRAINT "cem_prediction_market_signals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_session_files"
    ADD CONSTRAINT "cem_session_files_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_session_log"
    ADD CONSTRAINT "cem_session_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_sessions"
    ADD CONSTRAINT "cem_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_sessions"
    ADD CONSTRAINT "cem_sessions_session_id_key" UNIQUE ("session_id");



ALTER TABLE ONLY "public"."cem_ship_log"
    ADD CONSTRAINT "cem_ship_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_smart_alerts"
    ADD CONSTRAINT "cem_smart_alerts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategies"
    ADD CONSTRAINT "cem_strategies_parameter_hash_key" UNIQUE ("parameter_hash");



ALTER TABLE ONLY "public"."cem_strategies"
    ADD CONSTRAINT "cem_strategies_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategy_blocks"
    ADD CONSTRAINT "cem_strategy_blocks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategy_combos"
    ADD CONSTRAINT "cem_strategy_combos_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategy_library"
    ADD CONSTRAINT "cem_strategy_library_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategy_optimization"
    ADD CONSTRAINT "cem_strategy_optimization_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_strategy_results"
    ADD CONSTRAINT "cem_strategy_results_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_thresholds"
    ADD CONSTRAINT "cem_thresholds_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."cem_thresholds"
    ADD CONSTRAINT "cem_thresholds_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_todo"
    ADD CONSTRAINT "cem_todo_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_trade_copies"
    ADD CONSTRAINT "cem_trade_copies_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_trading_accounts"
    ADD CONSTRAINT "cem_trading_accounts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_user_library_progress"
    ADD CONSTRAINT "cem_user_library_progress_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_user_memory"
    ADD CONSTRAINT "cem_user_memory_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_user_profiles"
    ADD CONSTRAINT "cem_user_profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_user_profiles"
    ADD CONSTRAINT "cem_user_profiles_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."cem_user_uploads"
    ADD CONSTRAINT "cem_user_uploads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_users"
    ADD CONSTRAINT "cem_users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cem_users"
    ADD CONSTRAINT "cem_users_username_key" UNIQUE ("username");



ALTER TABLE ONLY "public"."cem_weather_trades"
    ADD CONSTRAINT "cem_weather_trades_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."conversations"
    ADD CONSTRAINT "conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."file_contents"
    ADD CONSTRAINT "file_contents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "files_agents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."files"
    ADD CONSTRAINT "files_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."groups_agents"
    ADD CONSTRAINT "groups_agents_pkey" PRIMARY KEY ("group_id", "agent_id");



ALTER TABLE ONLY "public"."groups_blocks"
    ADD CONSTRAINT "groups_blocks_pkey" PRIMARY KEY ("group_id", "block_id");



ALTER TABLE ONLY "public"."groups"
    ADD CONSTRAINT "groups_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."identities_agents"
    ADD CONSTRAINT "identities_agents_pkey" PRIMARY KEY ("identity_id", "agent_id");



ALTER TABLE ONLY "public"."identities_blocks"
    ADD CONSTRAINT "identities_blocks_pkey" PRIMARY KEY ("identity_id", "block_id");



ALTER TABLE ONLY "public"."identities"
    ADD CONSTRAINT "identities_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."jobs"
    ADD CONSTRAINT "jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."llm_batch_items"
    ADD CONSTRAINT "llm_batch_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."llm_batch_job"
    ADD CONSTRAINT "llm_batch_job_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mcp_oauth"
    ADD CONSTRAINT "mcp_oauth_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mcp_oauth"
    ADD CONSTRAINT "mcp_oauth_state_key" UNIQUE ("state");



ALTER TABLE ONLY "public"."mcp_server"
    ADD CONSTRAINT "mcp_server_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mcp_tools"
    ADD CONSTRAINT "mcp_tools_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_sequence_id_key" UNIQUE ("sequence_id");



ALTER TABLE ONLY "public"."orders"
    ADD CONSTRAINT "orders_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."orders"
    ADD CONSTRAINT "orders_stripe_session_id_key" UNIQUE ("stripe_session_id");



ALTER TABLE ONLY "public"."organizations"
    ADD CONSTRAINT "organizations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."passage_tags"
    ADD CONSTRAINT "passage_tags_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."prompts"
    ADD CONSTRAINT "prompts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."provider_models"
    ADD CONSTRAINT "provider_models_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."provider_trace_metadata"
    ADD CONSTRAINT "provider_trace_metadata_pkey" PRIMARY KEY ("created_at", "id");



ALTER TABLE ONLY "public"."provider_traces"
    ADD CONSTRAINT "provider_traces_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."providers"
    ADD CONSTRAINT "providers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."run_metrics"
    ADD CONSTRAINT "run_metrics_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."runs"
    ADD CONSTRAINT "runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sandbox_configs"
    ADD CONSTRAINT "sandbox_configs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sandbox_environment_variables"
    ADD CONSTRAINT "sandbox_environment_variables_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."source_passages"
    ADD CONSTRAINT "source_passages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sources_agents"
    ADD CONSTRAINT "sources_agents_pkey" PRIMARY KEY ("agent_id", "source_id");



ALTER TABLE ONLY "public"."sources"
    ADD CONSTRAINT "sources_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."steps"
    ADD CONSTRAINT "steps_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tools"
    ADD CONSTRAINT "tools_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."agent_environment_variables"
    ADD CONSTRAINT "uix_key_agent" UNIQUE ("key", "agent_id");



ALTER TABLE ONLY "public"."sandbox_environment_variables"
    ADD CONSTRAINT "uix_key_sandbox_config" UNIQUE ("key", "sandbox_config_id");



ALTER TABLE ONLY "public"."tools"
    ADD CONSTRAINT "uix_name_organization" UNIQUE ("name", "organization_id");



ALTER TABLE ONLY "public"."mcp_server"
    ADD CONSTRAINT "uix_name_organization_mcp_server" UNIQUE ("server_name", "organization_id");



ALTER TABLE ONLY "public"."tools"
    ADD CONSTRAINT "uix_organization_project_name" UNIQUE NULLS NOT DISTINCT ("organization_id", "project_id", "name");



ALTER TABLE ONLY "public"."sandbox_configs"
    ADD CONSTRAINT "uix_type_organization" UNIQUE ("type", "organization_id");



ALTER TABLE ONLY "public"."archives_agents"
    ADD CONSTRAINT "unique_agent_archive" UNIQUE ("agent_id");



ALTER TABLE ONLY "public"."blocks_agents"
    ADD CONSTRAINT "unique_agent_block" UNIQUE ("agent_id", "block_id");



ALTER TABLE ONLY "public"."agents_tags"
    ADD CONSTRAINT "unique_agent_tag" PRIMARY KEY ("agent_id", "tag");



ALTER TABLE ONLY "public"."tools_agents"
    ADD CONSTRAINT "unique_agent_tool" PRIMARY KEY ("agent_id", "tool_id");



ALTER TABLE ONLY "public"."block"
    ADD CONSTRAINT "unique_block_id_label" UNIQUE ("id", "label");



ALTER TABLE ONLY "public"."blocks_tags"
    ADD CONSTRAINT "unique_block_tag" PRIMARY KEY ("block_id", "tag");



ALTER TABLE ONLY "public"."blocks_conversations"
    ADD CONSTRAINT "unique_conversation_block" UNIQUE ("conversation_id", "block_id");



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "unique_conversation_message" UNIQUE ("conversation_id", "message_id");



ALTER TABLE ONLY "public"."provider_models"
    ADD CONSTRAINT "unique_handle_per_org_and_type" UNIQUE ("handle", "organization_id", "model_type");



ALTER TABLE ONLY "public"."identities"
    ADD CONSTRAINT "unique_identifier_key_project_id_organization_id" UNIQUE NULLS NOT DISTINCT ("identifier_key", "project_id", "organization_id");



ALTER TABLE ONLY "public"."blocks_agents"
    ADD CONSTRAINT "unique_label_per_agent" UNIQUE ("agent_id", "block_label");



ALTER TABLE ONLY "public"."blocks_conversations"
    ADD CONSTRAINT "unique_label_per_conversation" UNIQUE ("conversation_id", "block_label");



ALTER TABLE ONLY "public"."provider_models"
    ADD CONSTRAINT "unique_model_per_provider_and_type" UNIQUE ("name", "provider_id", "model_type");



ALTER TABLE ONLY "public"."providers"
    ADD CONSTRAINT "unique_name_organization_id" UNIQUE ("name", "organization_id");



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "uq_agent_filename" UNIQUE ("agent_id", "file_name");



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "uq_file_agent" UNIQUE ("file_id", "agent_id");



ALTER TABLE ONLY "public"."file_contents"
    ADD CONSTRAINT "uq_file_contents_file_id" UNIQUE ("file_id");



ALTER TABLE ONLY "public"."passage_tags"
    ADD CONSTRAINT "uq_passage_tag" UNIQUE ("passage_id", "tag");



ALTER TABLE ONLY "public"."provider_trace_metadata"
    ADD CONSTRAINT "uq_provider_trace_metadata_id" UNIQUE ("id");



ALTER TABLE ONLY "public"."sources"
    ADD CONSTRAINT "uq_source_name_organization" UNIQUE ("name", "organization_id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



CREATE INDEX "archival_passages_created_at_id_idx" ON "public"."archival_passages" USING "btree" ("created_at", "id");



CREATE INDEX "cem_bots_is_active_idx" ON "public"."cem_bots" USING "btree" ("is_active");



CREATE UNIQUE INDEX "cem_bots_token_idx" ON "public"."cem_bots" USING "btree" ("bot_token");



CREATE INDEX "cem_bots_user_email_idx" ON "public"."cem_bots" USING "btree" ("user_email");



CREATE INDEX "cem_context_embedding_idx" ON "public"."cem_context" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "cem_user_memory_embedding_idx" ON "public"."cem_user_memory" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "created_at_label_idx" ON "public"."block" USING "btree" ("created_at", "label");



CREATE INDEX "idx_account_trades_account" ON "public"."cem_account_trades" USING "btree" ("account_id");



CREATE INDEX "idx_agent_environment_variables_agent_id" ON "public"."agent_environment_variables" USING "btree" ("agent_id");



CREATE INDEX "idx_bot_delivery_jobs_status" ON "public"."bot_delivery_jobs" USING "btree" ("status");



CREATE INDEX "idx_bot_delivery_jobs_user_id" ON "public"."bot_delivery_jobs" USING "btree" ("user_id");



CREATE INDEX "idx_bot_perf_strategy" ON "public"."cem_bot_performance" USING "btree" ("strategy_id");



CREATE INDEX "idx_cem_decisions_category" ON "public"."cem_decisions" USING "btree" ("category");



CREATE INDEX "idx_cem_decisions_topic" ON "public"."cem_decisions" USING "btree" ("topic");



CREATE INDEX "idx_cem_knowledge_embeddings_vec" ON "public"."cem_knowledge_embeddings" USING "ivfflat" ("embedding" "public"."vector_cosine_ops") WITH ("lists"='50');



CREATE INDEX "idx_cem_knowledge_source" ON "public"."cem_knowledge_embeddings" USING "btree" ("source_table", "is_community");



CREATE INDEX "idx_cem_links_source" ON "public"."cem_links" USING "btree" ("source_id", "source_table");



CREATE INDEX "idx_cem_links_strength" ON "public"."cem_links" USING "btree" ("strength" DESC);



CREATE INDEX "idx_cem_links_target" ON "public"."cem_links" USING "btree" ("target_id", "target_table");



CREATE INDEX "idx_cem_links_type" ON "public"."cem_links" USING "btree" ("link_type");



CREATE INDEX "idx_cem_obs_compiled" ON "public"."cem_observations" USING "btree" ("compiled_truth" DESC, "created_at" DESC);



CREATE INDEX "idx_cem_obs_entities" ON "public"."cem_observations" USING "gin" ("entities");



CREATE INDEX "idx_cem_strategy_asset" ON "public"."cem_strategy_results" USING "btree" ("asset");



CREATE INDEX "idx_cem_strategy_created" ON "public"."cem_strategy_results" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_coach_research_asset" ON "public"."cem_coach_research" USING "btree" ("asset");



CREATE INDEX "idx_coach_research_created" ON "public"."cem_coach_research" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_coach_research_fts" ON "public"."cem_coach_research" USING "gin" ("fts");



CREATE INDEX "idx_community_posts_created" ON "public"."cem_community_posts" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_community_posts_user" ON "public"."cem_community_posts" USING "btree" ("user_id");



CREATE INDEX "idx_congress_live_created" ON "public"."cem_congress_live" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_congress_live_league" ON "public"."cem_congress_live" USING "btree" ("league_id");



CREATE INDEX "idx_congress_live_member" ON "public"."cem_congress_live" USING "btree" ("member_name");



CREATE INDEX "idx_conversations_session" ON "public"."cem_conversations" USING "btree" ("session_id");



CREATE INDEX "idx_conversations_tags" ON "public"."cem_conversations" USING "gin" ("tags");



CREATE INDEX "idx_conversations_user" ON "public"."cem_conversations" USING "btree" ("user_id");



CREATE INDEX "idx_curriculum_level" ON "public"."cem_curriculum_nodes" USING "btree" ("level");



CREATE INDEX "idx_curriculum_parent" ON "public"."cem_curriculum_nodes" USING "btree" ("parent_id");



CREATE INDEX "idx_curriculum_path" ON "public"."cem_curriculum_nodes" USING "btree" ("path");



CREATE UNIQUE INDEX "idx_curriculum_slug_parent" ON "public"."cem_curriculum_nodes" USING "btree" ("slug", COALESCE("parent_id", '00000000-0000-0000-0000-000000000000'::"uuid"));



CREATE INDEX "idx_embedding_queue_status" ON "public"."cem_embedding_queue" USING "btree" ("status", "queued_at");



CREATE INDEX "idx_episodes_cycle" ON "public"."cem_episodes" USING "btree" ("cycle_timestamp" DESC);



CREATE INDEX "idx_episodes_embedding" ON "public"."cem_episodes" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "idx_episodes_importance" ON "public"."cem_episodes" USING "btree" ("importance_score" DESC);



CREATE INDEX "idx_episodes_regime" ON "public"."cem_episodes" USING "gin" ("regime_context");



CREATE INDEX "idx_eureka_asset" ON "public"."cem_eureka_journal" USING "btree" ("asset");



CREATE INDEX "idx_eureka_community" ON "public"."cem_eureka_journal" USING "btree" ("is_community") WHERE ("is_community" = true);



CREATE INDEX "idx_eureka_journal_local_id" ON "public"."cem_eureka_journal" USING "btree" ("local_id");



CREATE INDEX "idx_eureka_user" ON "public"."cem_eureka_journal" USING "btree" ("user_id");



CREATE UNIQUE INDEX "idx_heartbeat_channel" ON "public"."cem_bot_heartbeats" USING "btree" ("channel_id");



CREATE INDEX "idx_insight_notes_asset" ON "public"."cem_insight_notes" USING "btree" ("asset");



CREATE INDEX "idx_insight_notes_related" ON "public"."cem_insight_notes" USING "gin" ("related_assets");



CREATE INDEX "idx_insight_notes_tags" ON "public"."cem_insight_notes" USING "gin" ("tags");



CREATE INDEX "idx_insight_notes_type" ON "public"."cem_insight_notes" USING "btree" ("note_type");



CREATE INDEX "idx_insights_accessed" ON "public"."cem_insights" USING "btree" ("last_accessed" DESC);



CREATE INDEX "idx_insights_embedding" ON "public"."cem_insights" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "idx_insights_importance" ON "public"."cem_insights" USING "btree" ("importance_score" DESC);



CREATE INDEX "idx_insights_tags" ON "public"."cem_insights" USING "gin" ("tags");



CREATE INDEX "idx_insights_type" ON "public"."cem_insights" USING "btree" ("insight_type");



CREATE INDEX "idx_instances_asset" ON "public"."cem_curriculum_instances" USING "btree" ("asset");



CREATE INDEX "idx_instances_node" ON "public"."cem_curriculum_instances" USING "btree" ("node_id");



CREATE INDEX "idx_instances_wr" ON "public"."cem_curriculum_instances" USING "btree" ("win_rate" DESC);



CREATE INDEX "idx_knowledge_source" ON "public"."cem_knowledge_embeddings" USING "btree" ("source_table");



CREATE INDEX "idx_known_fixes_category" ON "public"."cem_known_fixes" USING "btree" ("category");



CREATE INDEX "idx_known_fixes_problem" ON "public"."cem_known_fixes" USING "gin" ("to_tsvector"('"english"'::"regconfig", "problem"));



CREATE INDEX "idx_live_trades_asset" ON "public"."cem_live_trades" USING "btree" ("asset");



CREATE INDEX "idx_live_trades_asset_strategy" ON "public"."cem_live_trades" USING "btree" ("asset", "strategy_name", "status");



CREATE INDEX "idx_live_trades_channel" ON "public"."cem_live_trades" USING "btree" ("channel_id", "status", "created_at" DESC);



CREATE INDEX "idx_live_trades_created" ON "public"."cem_live_trades" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_live_trades_status_created" ON "public"."cem_live_trades" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "idx_market_snap_asset_date" ON "public"."cem_market_snapshots" USING "btree" ("asset", "snapshot_date");



CREATE INDEX "idx_marketplace_listings_type" ON "public"."cem_marketplace_listings" USING "btree" ("listing_type", "cem_approved");



CREATE INDEX "idx_messages_on_updated_at" ON "public"."messages" USING "btree" ("updated_at");



CREATE INDEX "idx_messages_step_id" ON "public"."messages" USING "btree" ("step_id");



CREATE INDEX "idx_observations_embedding" ON "public"."cem_observations" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "idx_observations_importance" ON "public"."cem_observations" USING "btree" ("importance_score" DESC);



CREATE INDEX "idx_observations_metadata" ON "public"."cem_observations" USING "gin" ("metadata");



CREATE INDEX "idx_observations_regime" ON "public"."cem_observations" USING "gin" ("regime_classification");



CREATE INDEX "idx_observations_symbol" ON "public"."cem_observations" USING "btree" ("symbol", "timestamp" DESC);



CREATE INDEX "idx_observations_time" ON "public"."cem_observations" USING "btree" ("timestamp" DESC);



CREATE INDEX "idx_ohlc_symbol_interval_time" ON "public"."cem_ohlc_cache" USING "btree" ("symbol", "interval", "time");



CREATE INDEX "idx_orders_stripe_session" ON "public"."orders" USING "btree" ("stripe_session_id");



CREATE INDEX "idx_orders_user_id" ON "public"."orders" USING "btree" ("user_id");



CREATE INDEX "idx_pattern_occ_symbol" ON "public"."cem_pattern_occurrences" USING "btree" ("symbol", "pattern_name");



CREATE INDEX "idx_portfolio_category" ON "public"."cem_portfolio" USING "btree" ("category");



CREATE INDEX "idx_portfolio_status" ON "public"."cem_portfolio" USING "btree" ("status");



CREATE INDEX "idx_pred_mkt_asset" ON "public"."cem_prediction_market_signals" USING "btree" ("related_asset");



CREATE INDEX "idx_pred_mkt_created" ON "public"."cem_prediction_market_signals" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_pred_mkt_platform" ON "public"."cem_prediction_market_signals" USING "btree" ("platform");



CREATE INDEX "idx_pred_mkt_status" ON "public"."cem_prediction_market_signals" USING "btree" ("trade_status");



CREATE INDEX "idx_sales_creator" ON "public"."cem_marketplace_sales" USING "btree" ("creator_id");



CREATE INDEX "idx_sales_strategy" ON "public"."cem_marketplace_sales" USING "btree" ("strategy_id");



CREATE INDEX "idx_session_files_user" ON "public"."cem_session_files" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "idx_session_log_date" ON "public"."cem_session_log" USING "btree" ("session_date" DESC);



CREATE INDEX "idx_strategies_asset" ON "public"."cem_strategies" USING "btree" ("asset_class");



CREATE INDEX "idx_strategies_created" ON "public"."cem_strategies" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_strategies_embedding" ON "public"."cem_strategies" USING "hnsw" ("embedding" "public"."vector_cosine_ops");



CREATE INDEX "idx_strategies_importance" ON "public"."cem_strategies" USING "btree" ("importance_score" DESC);



CREATE INDEX "idx_strategies_regime" ON "public"."cem_strategies" USING "gin" ("regime_tags");



CREATE INDEX "idx_strategies_type" ON "public"."cem_strategies" USING "btree" ("strategy_type");



CREATE INDEX "idx_strategies_validation" ON "public"."cem_strategies" USING "btree" ("validation_status");



CREATE INDEX "idx_strategy_asset_tier" ON "public"."cem_strategy_library" USING "btree" ("asset", "tier");



CREATE INDEX "idx_strategy_blocks_strategy" ON "public"."cem_strategy_blocks" USING "btree" ("strategy_id", "sort_order");



CREATE INDEX "idx_strategy_fts" ON "public"."cem_strategy_library" USING "gin" ("fts");



CREATE INDEX "idx_strategy_lib_asset" ON "public"."cem_strategy_library" USING "btree" ("asset");



CREATE INDEX "idx_strategy_lib_marketplace" ON "public"."cem_strategy_library" USING "btree" ("is_marketplace") WHERE ("is_marketplace" = true);



CREATE INDEX "idx_strategy_lib_tier" ON "public"."cem_strategy_library" USING "btree" ("tier");



CREATE INDEX "idx_strategy_results_asset" ON "public"."cem_strategy_results" USING "btree" ("asset_class", "asset");



CREATE INDEX "idx_strategy_results_return" ON "public"."cem_strategy_results" USING "btree" ("total_return" DESC);



CREATE INDEX "idx_strategy_results_score" ON "public"."cem_strategy_results" USING "btree" ("strategy_score" DESC);



CREATE INDEX "idx_strategy_results_session" ON "public"."cem_strategy_results" USING "btree" ("session_id");



CREATE INDEX "idx_strategy_results_sharpe" ON "public"."cem_strategy_results" USING "btree" ("sharpe_ratio" DESC NULLS LAST);



CREATE INDEX "idx_strategy_results_winner" ON "public"."cem_strategy_results" USING "btree" ("is_winner", "strategy_score" DESC);



CREATE INDEX "idx_strategy_timeframe" ON "public"."cem_strategy_library" USING "btree" ("timeframe");



CREATE INDEX "idx_trading_accounts_user" ON "public"."cem_trading_accounts" USING "btree" ("user_id");



CREATE INDEX "idx_uploads_user" ON "public"."cem_user_uploads" USING "btree" ("user_id");



CREATE INDEX "idx_weather_trades_category" ON "public"."cem_weather_trades" USING "btree" ("category");



CREATE INDEX "idx_weather_trades_platform" ON "public"."cem_weather_trades" USING "btree" ("platform");



CREATE INDEX "idx_weather_trades_status" ON "public"."cem_weather_trades" USING "btree" ("status");



CREATE INDEX "ix_agent_filename" ON "public"."files_agents" USING "btree" ("agent_id", "file_name");



CREATE INDEX "ix_agents_created_at" ON "public"."agents" USING "btree" ("created_at", "id");



CREATE INDEX "ix_agents_organization_id_created_by_id" ON "public"."agents" USING "btree" ("organization_id", "_created_by_id");



CREATE INDEX "ix_agents_organization_id_deployment_id" ON "public"."agents" USING "btree" ("organization_id", "deployment_id");



CREATE INDEX "ix_agents_project_id" ON "public"."agents" USING "btree" ("project_id");



CREATE INDEX "ix_agents_tags_agent_id_tag" ON "public"."agents_tags" USING "btree" ("agent_id", "tag");



CREATE INDEX "ix_agents_tags_tag_agent_id" ON "public"."agents_tags" USING "btree" ("tag", "agent_id");



CREATE INDEX "ix_archival_passages_archive_id" ON "public"."archival_passages" USING "btree" ("archive_id");



CREATE INDEX "ix_archival_passages_org_archive" ON "public"."archival_passages" USING "btree" ("organization_id", "archive_id");



CREATE INDEX "ix_archives_created_at" ON "public"."archives" USING "btree" ("created_at", "id");



CREATE INDEX "ix_archives_organization_id" ON "public"."archives" USING "btree" ("organization_id");



CREATE INDEX "ix_block_current_history_entry_id" ON "public"."block" USING "btree" ("current_history_entry_id");



CREATE INDEX "ix_block_hidden" ON "public"."block" USING "btree" ("hidden");



CREATE UNIQUE INDEX "ix_block_history_block_id_sequence" ON "public"."block_history" USING "btree" ("block_id", "sequence_number");



CREATE INDEX "ix_block_is_template" ON "public"."block" USING "btree" ("is_template");



CREATE INDEX "ix_block_org_project_template" ON "public"."block" USING "btree" ("organization_id", "project_id", "is_template");



CREATE INDEX "ix_block_organization_id_deployment_id" ON "public"."block" USING "btree" ("organization_id", "deployment_id");



CREATE INDEX "ix_blocks_agents_block_id" ON "public"."blocks_agents" USING "btree" ("block_id");



CREATE INDEX "ix_blocks_agents_block_label_agent_id" ON "public"."blocks_agents" USING "btree" ("block_label", "agent_id");



CREATE INDEX "ix_blocks_conversations_block_id" ON "public"."blocks_conversations" USING "btree" ("block_id");



CREATE INDEX "ix_blocks_tags_block_id_tag" ON "public"."blocks_tags" USING "btree" ("block_id", "tag");



CREATE INDEX "ix_blocks_tags_tag_block_id" ON "public"."blocks_tags" USING "btree" ("tag", "block_id");



CREATE INDEX "ix_conv_msg_agent_conversation" ON "public"."conversation_messages" USING "btree" ("agent_id", "conversation_id");



CREATE INDEX "ix_conv_msg_agent_id" ON "public"."conversation_messages" USING "btree" ("agent_id");



CREATE INDEX "ix_conv_msg_conversation_position" ON "public"."conversation_messages" USING "btree" ("conversation_id", "position");



CREATE INDEX "ix_conv_msg_message_id" ON "public"."conversation_messages" USING "btree" ("message_id");



CREATE INDEX "ix_conversations_agent_id" ON "public"."conversations" USING "btree" ("agent_id");



CREATE INDEX "ix_conversations_org_agent" ON "public"."conversations" USING "btree" ("organization_id", "agent_id");



CREATE INDEX "ix_conversations_org_agent_last_message_at" ON "public"."conversations" USING "btree" ("organization_id", "agent_id", "last_message_at");



CREATE INDEX "ix_file_agent" ON "public"."files_agents" USING "btree" ("file_id", "agent_id");



CREATE INDEX "ix_files_org_created" ON "public"."files" USING "btree" ("organization_id", "created_at" DESC);



CREATE INDEX "ix_files_processing_status" ON "public"."files" USING "btree" ("processing_status");



CREATE INDEX "ix_files_source_created" ON "public"."files" USING "btree" ("source_id", "created_at" DESC);



CREATE INDEX "ix_jobs_user_id" ON "public"."jobs" USING "btree" ("user_id");



CREATE INDEX "ix_llm_batch_items_agent_id" ON "public"."llm_batch_items" USING "btree" ("agent_id");



CREATE INDEX "ix_llm_batch_items_llm_batch_id" ON "public"."llm_batch_items" USING "btree" ("llm_batch_id");



CREATE INDEX "ix_llm_batch_items_status" ON "public"."llm_batch_items" USING "btree" ("request_status");



CREATE INDEX "ix_llm_batch_job_created_at" ON "public"."llm_batch_job" USING "btree" ("created_at");



CREATE INDEX "ix_llm_batch_job_status" ON "public"."llm_batch_job" USING "btree" ("status");



CREATE INDEX "ix_messages_agent_conversation_sequence" ON "public"."messages" USING "btree" ("agent_id", "conversation_id", "sequence_id");



CREATE INDEX "ix_messages_agent_created_at" ON "public"."messages" USING "btree" ("agent_id", "created_at");



CREATE INDEX "ix_messages_agent_sequence" ON "public"."messages" USING "btree" ("agent_id", "sequence_id");



CREATE INDEX "ix_messages_conversation_id" ON "public"."messages" USING "btree" ("conversation_id");



CREATE INDEX "ix_messages_created_at" ON "public"."messages" USING "btree" ("created_at", "id");



CREATE INDEX "ix_messages_org_agent" ON "public"."messages" USING "btree" ("organization_id", "agent_id");



CREATE INDEX "ix_messages_run_sequence" ON "public"."messages" USING "btree" ("run_id", "sequence_id");



CREATE INDEX "ix_passage_tags_org_archive" ON "public"."passage_tags" USING "btree" ("organization_id", "archive_id");



CREATE INDEX "ix_passage_tags_tag" ON "public"."passage_tags" USING "btree" ("tag");



CREATE INDEX "ix_provider_models_handle" ON "public"."provider_models" USING "btree" ("handle");



CREATE INDEX "ix_provider_models_model_type" ON "public"."provider_models" USING "btree" ("model_type");



CREATE INDEX "ix_provider_models_organization_id" ON "public"."provider_models" USING "btree" ("organization_id");



CREATE INDEX "ix_provider_models_provider_id" ON "public"."provider_models" USING "btree" ("provider_id");



CREATE INDEX "ix_provider_trace_metadata_step_id" ON "public"."provider_trace_metadata" USING "btree" ("step_id");



CREATE INDEX "ix_runs_agent_id" ON "public"."runs" USING "btree" ("agent_id");



CREATE INDEX "ix_runs_conversation_id" ON "public"."runs" USING "btree" ("conversation_id");



CREATE INDEX "ix_runs_created_at" ON "public"."runs" USING "btree" ("created_at", "id");



CREATE INDEX "ix_runs_organization_id" ON "public"."runs" USING "btree" ("organization_id");



CREATE INDEX "ix_sources_agents_source_id" ON "public"."sources_agents" USING "btree" ("source_id");



CREATE INDEX "ix_step_id" ON "public"."provider_traces" USING "btree" ("step_id");



CREATE INDEX "ix_step_metrics_run_id" ON "public"."step_metrics" USING "btree" ("run_id");



CREATE INDEX "ix_steps_run_id" ON "public"."steps" USING "btree" ("run_id");



CREATE INDEX "ix_tools_agents_tool_id" ON "public"."tools_agents" USING "btree" ("tool_id");



CREATE INDEX "ix_tools_created_at_name" ON "public"."tools" USING "btree" ("created_at", "name");



CREATE INDEX "ix_tools_organization_id" ON "public"."tools" USING "btree" ("organization_id");



CREATE INDEX "ix_tools_organization_id_name" ON "public"."tools" USING "btree" ("organization_id", "name");



CREATE INDEX "source_created_at_id_idx" ON "public"."sources" USING "btree" ("created_at", "id");



CREATE INDEX "source_passages_created_at_id_idx" ON "public"."source_passages" USING "btree" ("created_at", "id");



CREATE INDEX "source_passages_file_id_idx" ON "public"."source_passages" USING "btree" ("file_id");



CREATE INDEX "source_passages_org_idx" ON "public"."source_passages" USING "btree" ("organization_id");



CREATE OR REPLACE TRIGGER "cem_context_before_insert" BEFORE INSERT ON "public"."cem_context" FOR EACH ROW EXECUTE FUNCTION "public"."cem_context_upsert_trigger"();



CREATE OR REPLACE TRIGGER "cem_decisions_updated_at" BEFORE UPDATE ON "public"."cem_decisions" FOR EACH ROW EXECUTE FUNCTION "public"."update_cem_decisions_timestamp"();



CREATE OR REPLACE TRIGGER "trg_invalidate_old_bots" AFTER INSERT ON "public"."cem_bots" FOR EACH ROW EXECUTE FUNCTION "public"."invalidate_old_bots"();



CREATE OR REPLACE TRIGGER "trg_queue_journal_embed" AFTER INSERT OR UPDATE OF "insight" ON "public"."cem_eureka_journal" FOR EACH ROW EXECUTE FUNCTION "public"."_queue_journal_for_embedding"();



CREATE OR REPLACE TRIGGER "trg_queue_strategy_embed" AFTER INSERT OR UPDATE OF "is_winner", "strategy_score" ON "public"."cem_strategy_results" FOR EACH ROW EXECUTE FUNCTION "public"."_queue_strategy_for_embedding"();



CREATE OR REPLACE TRIGGER "trg_strategy_fts" BEFORE INSERT OR UPDATE ON "public"."cem_strategy_library" FOR EACH ROW EXECUTE FUNCTION "public"."_update_strategy_fts"();



CREATE OR REPLACE TRIGGER "update_bot_delivery_jobs_updated_at" BEFORE UPDATE ON "public"."bot_delivery_jobs" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_insights_updated_at" BEFORE UPDATE ON "public"."cem_insights" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_orders_updated_at" BEFORE UPDATE ON "public"."orders" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_strategies_updated_at" BEFORE UPDATE ON "public"."cem_strategies" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."agent_environment_variables"
    ADD CONSTRAINT "agent_environment_variables_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."agent_environment_variables"
    ADD CONSTRAINT "agent_environment_variables_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."agents"
    ADD CONSTRAINT "agents_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."agents_tags"
    ADD CONSTRAINT "agents_tags_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id");



ALTER TABLE ONLY "public"."archival_passages"
    ADD CONSTRAINT "archival_passages_archive_id_fkey" FOREIGN KEY ("archive_id") REFERENCES "public"."archives"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."archival_passages"
    ADD CONSTRAINT "archival_passages_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."archives_agents"
    ADD CONSTRAINT "archives_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."archives_agents"
    ADD CONSTRAINT "archives_agents_archive_id_fkey" FOREIGN KEY ("archive_id") REFERENCES "public"."archives"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."archives"
    ADD CONSTRAINT "archives_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."block_history"
    ADD CONSTRAINT "block_history_block_id_fkey" FOREIGN KEY ("block_id") REFERENCES "public"."block"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."block_history"
    ADD CONSTRAINT "block_history_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."block"
    ADD CONSTRAINT "block_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."blocks_agents"
    ADD CONSTRAINT "blocks_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."blocks_conversations"
    ADD CONSTRAINT "blocks_conversations_block_id_fkey" FOREIGN KEY ("block_id") REFERENCES "public"."block"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."blocks_conversations"
    ADD CONSTRAINT "blocks_conversations_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."blocks_tags"
    ADD CONSTRAINT "blocks_tags_block_id_fkey" FOREIGN KEY ("block_id") REFERENCES "public"."block"("id");



ALTER TABLE ONLY "public"."blocks_tags"
    ADD CONSTRAINT "blocks_tags_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."bot_delivery_jobs"
    ADD CONSTRAINT "bot_delivery_jobs_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "public"."orders"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."bot_delivery_jobs"
    ADD CONSTRAINT "bot_delivery_jobs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_account_trades"
    ADD CONSTRAINT "cem_account_trades_account_id_fkey" FOREIGN KEY ("account_id") REFERENCES "public"."cem_trading_accounts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_account_trades"
    ADD CONSTRAINT "cem_account_trades_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id");



ALTER TABLE ONLY "public"."cem_beta_invites"
    ADD CONSTRAINT "cem_beta_invites_used_by_fkey" FOREIGN KEY ("used_by") REFERENCES "public"."cem_users"("id");



ALTER TABLE ONLY "public"."cem_bot_performance"
    ADD CONSTRAINT "cem_bot_performance_bot_delivery_id_fkey" FOREIGN KEY ("bot_delivery_id") REFERENCES "public"."bot_delivery_jobs"("id");



ALTER TABLE ONLY "public"."cem_bot_performance"
    ADD CONSTRAINT "cem_bot_performance_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_bot_performance"
    ADD CONSTRAINT "cem_bot_performance_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_bots"
    ADD CONSTRAINT "cem_bots_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_community_follows"
    ADD CONSTRAINT "cem_community_follows_follower_id_fkey" FOREIGN KEY ("follower_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_community_follows"
    ADD CONSTRAINT "cem_community_follows_following_id_fkey" FOREIGN KEY ("following_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_community_insights"
    ADD CONSTRAINT "cem_community_insights_eureka_id_fkey" FOREIGN KEY ("eureka_id") REFERENCES "public"."cem_eureka_journal"("id");



ALTER TABLE ONLY "public"."cem_community_posts"
    ADD CONSTRAINT "cem_community_posts_account_id_fkey" FOREIGN KEY ("account_id") REFERENCES "public"."cem_trading_accounts"("id");



ALTER TABLE ONLY "public"."cem_community_posts"
    ADD CONSTRAINT "cem_community_posts_trade_id_fkey" FOREIGN KEY ("trade_id") REFERENCES "public"."cem_account_trades"("id");



ALTER TABLE ONLY "public"."cem_community_posts"
    ADD CONSTRAINT "cem_community_posts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_conversations"
    ADD CONSTRAINT "cem_conversations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_curriculum_connections"
    ADD CONSTRAINT "cem_curriculum_connections_instance_a_fkey" FOREIGN KEY ("instance_a") REFERENCES "public"."cem_curriculum_instances"("id");



ALTER TABLE ONLY "public"."cem_curriculum_connections"
    ADD CONSTRAINT "cem_curriculum_connections_instance_b_fkey" FOREIGN KEY ("instance_b") REFERENCES "public"."cem_curriculum_instances"("id");



ALTER TABLE ONLY "public"."cem_curriculum_instances"
    ADD CONSTRAINT "cem_curriculum_instances_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "public"."cem_curriculum_nodes"("id");



ALTER TABLE ONLY "public"."cem_curriculum_nodes"
    ADD CONSTRAINT "cem_curriculum_nodes_parent_id_fkey" FOREIGN KEY ("parent_id") REFERENCES "public"."cem_curriculum_nodes"("id");



ALTER TABLE ONLY "public"."cem_episodes"
    ADD CONSTRAINT "cem_episodes_distilled_to_insight_id_fkey" FOREIGN KEY ("distilled_to_insight_id") REFERENCES "public"."cem_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_eureka_journal"
    ADD CONSTRAINT "cem_eureka_journal_insight_note_id_fkey" FOREIGN KEY ("insight_note_id") REFERENCES "public"."cem_insight_notes"("id");



ALTER TABLE ONLY "public"."cem_eureka_journal"
    ADD CONSTRAINT "cem_eureka_journal_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_insight_notes"
    ADD CONSTRAINT "cem_insight_notes_curriculum_instance_id_fkey" FOREIGN KEY ("curriculum_instance_id") REFERENCES "public"."cem_curriculum_instances"("id");



ALTER TABLE ONLY "public"."cem_insight_notes"
    ADD CONSTRAINT "cem_insight_notes_curriculum_node_id_fkey" FOREIGN KEY ("curriculum_node_id") REFERENCES "public"."cem_curriculum_nodes"("id");



ALTER TABLE ONLY "public"."cem_insights"
    ADD CONSTRAINT "cem_insights_superseded_by_fkey" FOREIGN KEY ("superseded_by") REFERENCES "public"."cem_insights"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_marketplace_listings"
    ADD CONSTRAINT "cem_marketplace_listings_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_marketplace_listings"
    ADD CONSTRAINT "cem_marketplace_listings_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_marketplace_purchases"
    ADD CONSTRAINT "cem_marketplace_purchases_buyer_id_fkey" FOREIGN KEY ("buyer_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_marketplace_purchases"
    ADD CONSTRAINT "cem_marketplace_purchases_listing_id_fkey" FOREIGN KEY ("listing_id") REFERENCES "public"."cem_marketplace_listings"("id");



ALTER TABLE ONLY "public"."cem_marketplace_reviews"
    ADD CONSTRAINT "cem_marketplace_reviews_listing_id_fkey" FOREIGN KEY ("listing_id") REFERENCES "public"."cem_marketplace_listings"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_marketplace_reviews"
    ADD CONSTRAINT "cem_marketplace_reviews_reviewer_id_fkey" FOREIGN KEY ("reviewer_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_marketplace_sales"
    ADD CONSTRAINT "cem_marketplace_sales_buyer_id_fkey" FOREIGN KEY ("buyer_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_marketplace_sales"
    ADD CONSTRAINT "cem_marketplace_sales_creator_id_fkey" FOREIGN KEY ("creator_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_marketplace_sales"
    ADD CONSTRAINT "cem_marketplace_sales_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_session_files"
    ADD CONSTRAINT "cem_session_files_account_id_fkey" FOREIGN KEY ("account_id") REFERENCES "public"."cem_trading_accounts"("id");



ALTER TABLE ONLY "public"."cem_session_files"
    ADD CONSTRAINT "cem_session_files_previous_session_id_fkey" FOREIGN KEY ("previous_session_id") REFERENCES "public"."cem_session_files"("id");



ALTER TABLE ONLY "public"."cem_session_files"
    ADD CONSTRAINT "cem_session_files_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_session_files"
    ADD CONSTRAINT "cem_session_files_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_smart_alerts"
    ADD CONSTRAINT "cem_smart_alerts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_strategies"
    ADD CONSTRAINT "cem_strategies_lineage_parent_id_fkey" FOREIGN KEY ("lineage_parent_id") REFERENCES "public"."cem_strategies"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_strategy_blocks"
    ADD CONSTRAINT "cem_strategy_blocks_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_strategy_library"
    ADD CONSTRAINT "cem_strategy_library_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."cem_trade_copies"
    ADD CONSTRAINT "cem_trade_copies_copying_account_id_fkey" FOREIGN KEY ("copying_account_id") REFERENCES "public"."cem_trading_accounts"("id");



ALTER TABLE ONLY "public"."cem_trade_copies"
    ADD CONSTRAINT "cem_trade_copies_copying_user_id_fkey" FOREIGN KEY ("copying_user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_trade_copies"
    ADD CONSTRAINT "cem_trade_copies_original_trade_id_fkey" FOREIGN KEY ("original_trade_id") REFERENCES "public"."cem_account_trades"("id");



ALTER TABLE ONLY "public"."cem_trade_copies"
    ADD CONSTRAINT "cem_trade_copies_original_user_id_fkey" FOREIGN KEY ("original_user_id") REFERENCES "public"."cem_users"("id");



ALTER TABLE ONLY "public"."cem_trading_accounts"
    ADD CONSTRAINT "cem_trading_accounts_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_trading_accounts"
    ADD CONSTRAINT "cem_trading_accounts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cem_user_library_progress"
    ADD CONSTRAINT "cem_user_library_progress_lesson_id_fkey" FOREIGN KEY ("lesson_id") REFERENCES "public"."cem_library_lessons"("id");



ALTER TABLE ONLY "public"."cem_user_uploads"
    ADD CONSTRAINT "cem_user_uploads_strategy_built_fkey" FOREIGN KEY ("strategy_built") REFERENCES "public"."cem_strategy_library"("id");



ALTER TABLE ONLY "public"."cem_user_uploads"
    ADD CONSTRAINT "cem_user_uploads_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "public"."messages"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversation_messages"
    ADD CONSTRAINT "conversation_messages_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."conversations"
    ADD CONSTRAINT "conversations_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."conversations"
    ADD CONSTRAINT "conversations_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."file_contents"
    ADD CONSTRAINT "file_contents_file_id_fkey" FOREIGN KEY ("file_id") REFERENCES "public"."files"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "files_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "files_agents_file_id_fkey" FOREIGN KEY ("file_id") REFERENCES "public"."files"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "files_agents_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."files_agents"
    ADD CONSTRAINT "files_agents_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."files"
    ADD CONSTRAINT "files_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."files"
    ADD CONSTRAINT "files_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."block"
    ADD CONSTRAINT "fk_block_current_history_entry" FOREIGN KEY ("current_history_entry_id") REFERENCES "public"."block_history"("id");



ALTER TABLE ONLY "public"."blocks_agents"
    ADD CONSTRAINT "fk_block_id_label" FOREIGN KEY ("block_id", "block_label") REFERENCES "public"."block"("id", "label") ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE;



ALTER TABLE ONLY "public"."groups_agents"
    ADD CONSTRAINT "groups_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."groups_agents"
    ADD CONSTRAINT "groups_agents_group_id_fkey" FOREIGN KEY ("group_id") REFERENCES "public"."groups"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."groups_blocks"
    ADD CONSTRAINT "groups_blocks_block_id_fkey" FOREIGN KEY ("block_id") REFERENCES "public"."block"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."groups_blocks"
    ADD CONSTRAINT "groups_blocks_group_id_fkey" FOREIGN KEY ("group_id") REFERENCES "public"."groups"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."groups"
    ADD CONSTRAINT "groups_manager_agent_id_fkey" FOREIGN KEY ("manager_agent_id") REFERENCES "public"."agents"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."groups"
    ADD CONSTRAINT "groups_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."identities_agents"
    ADD CONSTRAINT "identities_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."identities_agents"
    ADD CONSTRAINT "identities_agents_identity_id_fkey" FOREIGN KEY ("identity_id") REFERENCES "public"."identities"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."identities_blocks"
    ADD CONSTRAINT "identities_blocks_block_id_fkey" FOREIGN KEY ("block_id") REFERENCES "public"."block"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."identities_blocks"
    ADD CONSTRAINT "identities_blocks_identity_id_fkey" FOREIGN KEY ("identity_id") REFERENCES "public"."identities"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."identities"
    ADD CONSTRAINT "identities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."jobs"
    ADD CONSTRAINT "jobs_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."jobs"
    ADD CONSTRAINT "jobs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."llm_batch_items"
    ADD CONSTRAINT "llm_batch_items_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."llm_batch_items"
    ADD CONSTRAINT "llm_batch_items_llm_batch_id_fkey" FOREIGN KEY ("llm_batch_id") REFERENCES "public"."llm_batch_job"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."llm_batch_items"
    ADD CONSTRAINT "llm_batch_items_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."llm_batch_job"
    ADD CONSTRAINT "llm_batch_job_letta_batch_job_id_fkey" FOREIGN KEY ("letta_batch_job_id") REFERENCES "public"."jobs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."llm_batch_job"
    ADD CONSTRAINT "llm_batch_job_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."mcp_oauth"
    ADD CONSTRAINT "mcp_oauth_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."mcp_oauth"
    ADD CONSTRAINT "mcp_oauth_server_id_fkey" FOREIGN KEY ("server_id") REFERENCES "public"."mcp_server"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."mcp_oauth"
    ADD CONSTRAINT "mcp_oauth_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."mcp_server"
    ADD CONSTRAINT "mcp_server_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."mcp_tools"
    ADD CONSTRAINT "mcp_tools_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."runs"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_step_id_fkey" FOREIGN KEY ("step_id") REFERENCES "public"."steps"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."orders"
    ADD CONSTRAINT "orders_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."cem_users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."passage_tags"
    ADD CONSTRAINT "passage_tags_archive_id_fkey" FOREIGN KEY ("archive_id") REFERENCES "public"."archives"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."passage_tags"
    ADD CONSTRAINT "passage_tags_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."passage_tags"
    ADD CONSTRAINT "passage_tags_passage_id_fkey" FOREIGN KEY ("passage_id") REFERENCES "public"."archival_passages"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."provider_models"
    ADD CONSTRAINT "provider_models_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."provider_models"
    ADD CONSTRAINT "provider_models_provider_id_fkey" FOREIGN KEY ("provider_id") REFERENCES "public"."providers"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."provider_trace_metadata"
    ADD CONSTRAINT "provider_trace_metadata_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."provider_traces"
    ADD CONSTRAINT "provider_traces_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."providers"
    ADD CONSTRAINT "providers_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."run_metrics"
    ADD CONSTRAINT "run_metrics_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."run_metrics"
    ADD CONSTRAINT "run_metrics_id_fkey" FOREIGN KEY ("id") REFERENCES "public"."runs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."run_metrics"
    ADD CONSTRAINT "run_metrics_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."runs"
    ADD CONSTRAINT "runs_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id");



ALTER TABLE ONLY "public"."runs"
    ADD CONSTRAINT "runs_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."runs"
    ADD CONSTRAINT "runs_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."sandbox_configs"
    ADD CONSTRAINT "sandbox_configs_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."sandbox_environment_variables"
    ADD CONSTRAINT "sandbox_environment_variables_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."sandbox_environment_variables"
    ADD CONSTRAINT "sandbox_environment_variables_sandbox_config_id_fkey" FOREIGN KEY ("sandbox_config_id") REFERENCES "public"."sandbox_configs"("id");



ALTER TABLE ONLY "public"."source_passages"
    ADD CONSTRAINT "source_passages_file_id_fkey" FOREIGN KEY ("file_id") REFERENCES "public"."files"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."source_passages"
    ADD CONSTRAINT "source_passages_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."source_passages"
    ADD CONSTRAINT "source_passages_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sources_agents"
    ADD CONSTRAINT "sources_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sources_agents"
    ADD CONSTRAINT "sources_agents_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sources"
    ADD CONSTRAINT "sources_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_id_fkey" FOREIGN KEY ("id") REFERENCES "public"."steps"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_provider_id_fkey" FOREIGN KEY ("provider_id") REFERENCES "public"."providers"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."step_metrics"
    ADD CONSTRAINT "step_metrics_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."runs"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."steps"
    ADD CONSTRAINT "steps_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."steps"
    ADD CONSTRAINT "steps_provider_id_fkey" FOREIGN KEY ("provider_id") REFERENCES "public"."providers"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."steps"
    ADD CONSTRAINT "steps_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."runs"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."tools_agents"
    ADD CONSTRAINT "tools_agents_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tools_agents"
    ADD CONSTRAINT "tools_agents_tool_id_fkey" FOREIGN KEY ("tool_id") REFERENCES "public"."tools"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tools"
    ADD CONSTRAINT "tools_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



CREATE POLICY "Allow all reads" ON "public"."cem_links" FOR SELECT USING (true);



CREATE POLICY "Allow anon delete on github_staging" ON "public"."cem_github_staging" FOR DELETE USING (true);



CREATE POLICY "Allow anon insert on github_staging" ON "public"."cem_github_staging" FOR INSERT WITH CHECK (true);



CREATE POLICY "Allow anon read on github_staging" ON "public"."cem_github_staging" FOR SELECT USING (true);



CREATE POLICY "Allow anon update on github_staging" ON "public"."cem_github_staging" FOR UPDATE USING (true);



CREATE POLICY "Allow authenticated inserts" ON "public"."cem_links" FOR INSERT TO "authenticated" WITH CHECK (true);



CREATE POLICY "Service role full access bot jobs" ON "public"."bot_delivery_jobs" USING ((( SELECT "auth"."role"() AS "role") = 'service_role'::"text"));



CREATE POLICY "Service role full access orders" ON "public"."orders" USING ((( SELECT "auth"."role"() AS "role") = 'service_role'::"text"));



CREATE POLICY "Users can view own bot jobs" ON "public"."bot_delivery_jobs" FOR SELECT USING ((( SELECT "auth"."uid"() AS "uid") = "user_id"));



CREATE POLICY "Users can view own orders" ON "public"."orders" FOR SELECT USING ((( SELECT "auth"."uid"() AS "uid") = "user_id"));



CREATE POLICY "anon_all_cem_sessions" ON "public"."cem_sessions" TO "anon" USING (true) WITH CHECK (true);



CREATE POLICY "anon_all_cem_user_memory" ON "public"."cem_user_memory" TO "anon" USING (true) WITH CHECK (true);



CREATE POLICY "anon_all_cem_user_profiles" ON "public"."cem_user_profiles" TO "anon" USING (true) WITH CHECK (true);



CREATE POLICY "anon_insert_cem_strategy_results" ON "public"."cem_strategy_results" FOR INSERT TO "anon" WITH CHECK (true);



CREATE POLICY "anon_read" ON "public"."cem_episodes" FOR SELECT TO "anon" USING (true);



CREATE POLICY "anon_read" ON "public"."cem_insights" FOR SELECT TO "anon" USING (true);



CREATE POLICY "anon_read" ON "public"."cem_observations" FOR SELECT TO "anon" USING (true);



CREATE POLICY "anon_read" ON "public"."cem_strategies" FOR SELECT TO "anon" USING (true);



CREATE POLICY "anon_select_cem_strategy_results" ON "public"."cem_strategy_results" FOR SELECT TO "anon" USING (true);



ALTER TABLE "public"."bot_delivery_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_bot_performance" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_bots" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_community_insights" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_context" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_conversations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_curriculum_connections" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_curriculum_instances" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_curriculum_nodes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_embedding_queue" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_episodes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_eureka_journal" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_github_staging" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_insight_notes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_insights" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_knowledge_embeddings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_links" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_live_trades" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_market_snapshots" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_marketplace_sales" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_observations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_ohlc_cache" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_pattern_occurrences" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_portfolio" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_session_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_ship_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_strategies" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_strategy_combos" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_strategy_library" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_strategy_optimization" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_strategy_results" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_todo" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_user_memory" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_user_profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_user_uploads" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cem_users" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "community_insights_public_read" ON "public"."cem_community_insights" FOR SELECT USING (true);



CREATE POLICY "market_snapshots_public_read" ON "public"."cem_market_snapshots" FOR SELECT USING (true);



ALTER TABLE "public"."orders" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "public_read_cem_context" ON "public"."cem_context" FOR SELECT TO "anon" USING (true);



CREATE POLICY "public_write_cem_context" ON "public"."cem_context" TO "anon" USING (true) WITH CHECK (true);



CREATE POLICY "service_all" ON "public"."cem_episodes" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all" ON "public"."cem_insights" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all" ON "public"."cem_observations" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all" ON "public"."cem_strategies" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all_cem_sessions" ON "public"."cem_sessions" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all_cem_user_memory" ON "public"."cem_user_memory" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_all_cem_user_profiles" ON "public"."cem_user_profiles" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_full_access" ON "public"."cem_bots" USING (true) WITH CHECK (true);



CREATE POLICY "service_role_full_access_cem_strategy_results" ON "public"."cem_strategy_results" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_role_full_access_cem_users" ON "public"."cem_users" TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "service_role_only_cem_portfolio" ON "public"."cem_portfolio" USING (("auth"."role"() = 'service_role'::"text")) WITH CHECK (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "strategy_library_public_read" ON "public"."cem_strategy_library" FOR SELECT USING ((("is_marketplace" = true) OR ("is_anonymous" = true)));





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "service_role";






















































































































































GRANT ALL ON FUNCTION "public"."_queue_journal_for_embedding"() TO "anon";
GRANT ALL ON FUNCTION "public"."_queue_journal_for_embedding"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."_queue_journal_for_embedding"() TO "service_role";



GRANT ALL ON FUNCTION "public"."_queue_strategy_for_embedding"() TO "anon";
GRANT ALL ON FUNCTION "public"."_queue_strategy_for_embedding"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."_queue_strategy_for_embedding"() TO "service_role";



GRANT ALL ON FUNCTION "public"."_update_strategy_fts"() TO "anon";
GRANT ALL ON FUNCTION "public"."_update_strategy_fts"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."_update_strategy_fts"() TO "service_role";



GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."cem_context_upsert_trigger"() TO "anon";
GRANT ALL ON FUNCTION "public"."cem_context_upsert_trigger"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."cem_context_upsert_trigger"() TO "service_role";



GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."fts_search_strategies"("query_text" "text", "match_count" integer, "asset_filter" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."fts_search_strategies"("query_text" "text", "match_count" integer, "asset_filter" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."fts_search_strategies"("query_text" "text", "match_count" integer, "asset_filter" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "postgres";
GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "anon";
GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "authenticated";
GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "service_role";



GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."hybrid_search_strategies"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer, "asset_filter" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."hybrid_search_strategies"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer, "asset_filter" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."hybrid_search_strategies"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer, "asset_filter" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."insert_claude_batch"("data" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."insert_claude_batch"("data" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."insert_claude_batch"("data" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."invalidate_old_bots"() TO "anon";
GRANT ALL ON FUNCTION "public"."invalidate_old_bots"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."invalidate_old_bots"() TO "service_role";



GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "postgres";
GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "anon";
GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "authenticated";
GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "service_role";



GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "postgres";
GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "anon";
GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "authenticated";
GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "service_role";



GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."match_cem_episodes"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_cem_episodes"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_cem_episodes"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_cem_insights"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_cem_insights"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_cem_insights"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_cem_knowledge"("query_embedding" "public"."vector", "match_threshold" double precision, "match_count" integer, "filter_community" boolean) TO "anon";
GRANT ALL ON FUNCTION "public"."match_cem_knowledge"("query_embedding" "public"."vector", "match_threshold" double precision, "match_count" integer, "filter_community" boolean) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_cem_knowledge"("query_embedding" "public"."vector", "match_threshold" double precision, "match_count" integer, "filter_community" boolean) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_cem_observations"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_cem_observations"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_cem_observations"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_cem_strategies"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_cem_strategies"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_cem_strategies"("query_embedding" "public"."vector", "similarity_threshold" double precision, "top_k" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_community_patterns"("query_embedding" "public"."vector", "match_count" integer, "min_confidence" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."match_community_patterns"("query_embedding" "public"."vector", "match_count" integer, "min_confidence" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_community_patterns"("query_embedding" "public"."vector", "match_count" integer, "min_confidence" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."match_documents"("query_embedding" "public"."vector", "match_count" integer, "filter" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."match_documents"("query_embedding" "public"."vector", "match_count" integer, "filter" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_documents"("query_embedding" "public"."vector", "match_count" integer, "filter" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."match_user_memories"("query_embedding" "public"."vector", "match_user_id" "text", "match_count" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_user_memories"("query_embedding" "public"."vector", "match_user_id" "text", "match_count" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_user_memories"("query_embedding" "public"."vector", "match_user_id" "text", "match_count" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."search_brain"("query_embedding" "public"."vector", "match_count" integer, "min_similarity" double precision) TO "anon";
GRANT ALL ON FUNCTION "public"."search_brain"("query_embedding" "public"."vector", "match_count" integer, "min_similarity" double precision) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_brain"("query_embedding" "public"."vector", "match_count" integer, "min_similarity" double precision) TO "service_role";



GRANT ALL ON FUNCTION "public"."search_knowledge"("query_embedding" "public"."vector", "match_count" integer, "source_filter" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."search_knowledge"("query_embedding" "public"."vector", "match_count" integer, "source_filter" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_knowledge"("query_embedding" "public"."vector", "match_count" integer, "source_filter" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."search_library"("query_embedding" "public"."vector", "match_table" "text", "match_count" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."search_library"("query_embedding" "public"."vector", "match_table" "text", "match_count" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_library"("query_embedding" "public"."vector", "match_table" "text", "match_count" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "anon";
GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "service_role";



GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "anon";
GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "postgres";
GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "anon";
GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."unified_knowledge_search"("query_text" "text", "match_count" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."unified_knowledge_search"("query_text" "text", "match_count" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."unified_knowledge_search"("query_text" "text", "match_count" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_academy_leaderboard"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_academy_leaderboard"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_academy_leaderboard"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_cem_decisions_timestamp"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_cem_decisions_timestamp"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_cem_decisions_timestamp"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON FUNCTION "public"."upsert_brain"("p_key" "text", "p_value" "text", "p_updated_by" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."upsert_brain"("p_key" "text", "p_value" "text", "p_updated_by" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."upsert_brain"("p_key" "text", "p_value" "text", "p_updated_by" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "anon";
GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "service_role";












GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "service_role";



GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "postgres";
GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "anon";
GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "service_role";



GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "postgres";
GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "anon";
GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "authenticated";
GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "service_role";









GRANT ALL ON TABLE "public"."agent_environment_variables" TO "anon";
GRANT ALL ON TABLE "public"."agent_environment_variables" TO "authenticated";
GRANT ALL ON TABLE "public"."agent_environment_variables" TO "service_role";



GRANT ALL ON TABLE "public"."agents" TO "anon";
GRANT ALL ON TABLE "public"."agents" TO "authenticated";
GRANT ALL ON TABLE "public"."agents" TO "service_role";



GRANT ALL ON TABLE "public"."agents_tags" TO "anon";
GRANT ALL ON TABLE "public"."agents_tags" TO "authenticated";
GRANT ALL ON TABLE "public"."agents_tags" TO "service_role";



GRANT ALL ON TABLE "public"."archival_passages" TO "anon";
GRANT ALL ON TABLE "public"."archival_passages" TO "authenticated";
GRANT ALL ON TABLE "public"."archival_passages" TO "service_role";



GRANT ALL ON TABLE "public"."archives" TO "anon";
GRANT ALL ON TABLE "public"."archives" TO "authenticated";
GRANT ALL ON TABLE "public"."archives" TO "service_role";



GRANT ALL ON TABLE "public"."archives_agents" TO "anon";
GRANT ALL ON TABLE "public"."archives_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."archives_agents" TO "service_role";



GRANT ALL ON TABLE "public"."block" TO "anon";
GRANT ALL ON TABLE "public"."block" TO "authenticated";
GRANT ALL ON TABLE "public"."block" TO "service_role";



GRANT ALL ON TABLE "public"."block_history" TO "anon";
GRANT ALL ON TABLE "public"."block_history" TO "authenticated";
GRANT ALL ON TABLE "public"."block_history" TO "service_role";



GRANT ALL ON TABLE "public"."blocks_agents" TO "anon";
GRANT ALL ON TABLE "public"."blocks_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."blocks_agents" TO "service_role";



GRANT ALL ON TABLE "public"."blocks_conversations" TO "anon";
GRANT ALL ON TABLE "public"."blocks_conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."blocks_conversations" TO "service_role";



GRANT ALL ON TABLE "public"."blocks_tags" TO "anon";
GRANT ALL ON TABLE "public"."blocks_tags" TO "authenticated";
GRANT ALL ON TABLE "public"."blocks_tags" TO "service_role";



GRANT ALL ON TABLE "public"."bot_delivery_jobs" TO "anon";
GRANT ALL ON TABLE "public"."bot_delivery_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_delivery_jobs" TO "service_role";



GRANT ALL ON TABLE "public"."cem_account_trades" TO "anon";
GRANT ALL ON TABLE "public"."cem_account_trades" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_account_trades" TO "service_role";



GRANT ALL ON TABLE "public"."cem_beta_invites" TO "anon";
GRANT ALL ON TABLE "public"."cem_beta_invites" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_beta_invites" TO "service_role";



GRANT ALL ON TABLE "public"."cem_bot_heartbeats" TO "anon";
GRANT ALL ON TABLE "public"."cem_bot_heartbeats" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_bot_heartbeats" TO "service_role";



GRANT ALL ON TABLE "public"."cem_bot_performance" TO "anon";
GRANT ALL ON TABLE "public"."cem_bot_performance" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_bot_performance" TO "service_role";



GRANT ALL ON TABLE "public"."cem_bots" TO "anon";
GRANT ALL ON TABLE "public"."cem_bots" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_bots" TO "service_role";



GRANT ALL ON TABLE "public"."cem_live_trades" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_live_trades" TO "service_role";



GRANT ALL ON TABLE "public"."cem_channel_performance" TO "anon";
GRANT ALL ON TABLE "public"."cem_channel_performance" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_channel_performance" TO "service_role";



GRANT ALL ON TABLE "public"."cem_coach_research" TO "anon";
GRANT ALL ON TABLE "public"."cem_coach_research" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_coach_research" TO "service_role";



GRANT ALL ON TABLE "public"."cem_community_follows" TO "anon";
GRANT ALL ON TABLE "public"."cem_community_follows" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_community_follows" TO "service_role";



GRANT ALL ON TABLE "public"."cem_community_insights" TO "anon";
GRANT ALL ON TABLE "public"."cem_community_insights" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_community_insights" TO "service_role";



GRANT ALL ON TABLE "public"."cem_community_posts" TO "anon";
GRANT ALL ON TABLE "public"."cem_community_posts" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_community_posts" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategy_results" TO "anon";
GRANT ALL ON TABLE "public"."cem_strategy_results" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategy_results" TO "service_role";



GRANT ALL ON TABLE "public"."cem_community_stats" TO "anon";
GRANT ALL ON TABLE "public"."cem_community_stats" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_community_stats" TO "service_role";



GRANT ALL ON TABLE "public"."cem_congress_live" TO "anon";
GRANT ALL ON TABLE "public"."cem_congress_live" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_congress_live" TO "service_role";



GRANT ALL ON TABLE "public"."cem_context" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_context" TO "service_role";



GRANT ALL ON TABLE "public"."cem_conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_conversations" TO "service_role";
GRANT SELECT ON TABLE "public"."cem_conversations" TO "anon";



GRANT ALL ON TABLE "public"."cem_curriculum_connections" TO "anon";
GRANT ALL ON TABLE "public"."cem_curriculum_connections" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_curriculum_connections" TO "service_role";



GRANT ALL ON TABLE "public"."cem_curriculum_instances" TO "anon";
GRANT ALL ON TABLE "public"."cem_curriculum_instances" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_curriculum_instances" TO "service_role";



GRANT ALL ON TABLE "public"."cem_curriculum_nodes" TO "anon";
GRANT ALL ON TABLE "public"."cem_curriculum_nodes" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_curriculum_nodes" TO "service_role";



GRANT ALL ON TABLE "public"."cem_decisions" TO "anon";
GRANT ALL ON TABLE "public"."cem_decisions" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_decisions" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_decisions_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_decisions_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_decisions_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_embedding_queue" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_embedding_queue" TO "service_role";



GRANT ALL ON TABLE "public"."cem_episodes" TO "anon";
GRANT ALL ON TABLE "public"."cem_episodes" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_episodes" TO "service_role";



GRANT ALL ON TABLE "public"."cem_eureka_journal" TO "anon";
GRANT ALL ON TABLE "public"."cem_eureka_journal" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_eureka_journal" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_eureka_journal_journal_number_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_eureka_journal_journal_number_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_eureka_journal_journal_number_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_github_staging" TO "anon";
GRANT ALL ON TABLE "public"."cem_github_staging" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_github_staging" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_github_staging_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_github_staging_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_github_staging_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_indicator_isolation" TO "anon";
GRANT ALL ON TABLE "public"."cem_indicator_isolation" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_indicator_isolation" TO "service_role";



GRANT ALL ON TABLE "public"."cem_insight_notes" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_insight_notes" TO "service_role";



GRANT ALL ON TABLE "public"."cem_insights" TO "anon";
GRANT ALL ON TABLE "public"."cem_insights" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_insights" TO "service_role";



GRANT ALL ON TABLE "public"."cem_invite_codes" TO "anon";
GRANT ALL ON TABLE "public"."cem_invite_codes" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_invite_codes" TO "service_role";



GRANT ALL ON TABLE "public"."cem_knowledge_embeddings" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_knowledge_embeddings" TO "service_role";



GRANT ALL ON TABLE "public"."cem_known_fixes" TO "anon";
GRANT ALL ON TABLE "public"."cem_known_fixes" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_known_fixes" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_known_fixes_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_known_fixes_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_known_fixes_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_library_lessons" TO "anon";
GRANT ALL ON TABLE "public"."cem_library_lessons" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_library_lessons" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_library_lessons_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_library_lessons_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_library_lessons_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_links" TO "anon";
GRANT ALL ON TABLE "public"."cem_links" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_links" TO "service_role";



GRANT ALL ON TABLE "public"."cem_market_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."cem_market_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_market_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."cem_marketplace_listings" TO "anon";
GRANT ALL ON TABLE "public"."cem_marketplace_listings" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_marketplace_listings" TO "service_role";



GRANT ALL ON TABLE "public"."cem_marketplace_purchases" TO "anon";
GRANT ALL ON TABLE "public"."cem_marketplace_purchases" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_marketplace_purchases" TO "service_role";



GRANT ALL ON TABLE "public"."cem_marketplace_reviews" TO "anon";
GRANT ALL ON TABLE "public"."cem_marketplace_reviews" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_marketplace_reviews" TO "service_role";



GRANT ALL ON TABLE "public"."cem_marketplace_sales" TO "anon";
GRANT ALL ON TABLE "public"."cem_marketplace_sales" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_marketplace_sales" TO "service_role";



GRANT ALL ON TABLE "public"."cem_observations" TO "anon";
GRANT ALL ON TABLE "public"."cem_observations" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_observations" TO "service_role";



GRANT ALL ON TABLE "public"."cem_ohlc_cache" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_ohlc_cache" TO "service_role";



GRANT ALL ON TABLE "public"."cem_pattern_occurrences" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_pattern_occurrences" TO "service_role";



GRANT ALL ON TABLE "public"."cem_portfolio" TO "anon";
GRANT ALL ON TABLE "public"."cem_portfolio" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_portfolio" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_portfolio_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_portfolio_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_portfolio_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_prediction_market_signals" TO "anon";
GRANT ALL ON TABLE "public"."cem_prediction_market_signals" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_prediction_market_signals" TO "service_role";



GRANT ALL ON TABLE "public"."cem_session_files" TO "anon";
GRANT ALL ON TABLE "public"."cem_session_files" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_session_files" TO "service_role";



GRANT ALL ON TABLE "public"."cem_session_log" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_session_log" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_session_log_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_session_log_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_session_log_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_sessions" TO "anon";
GRANT ALL ON TABLE "public"."cem_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_sessions" TO "service_role";



GRANT ALL ON TABLE "public"."cem_ship_log" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_ship_log" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_ship_log_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_ship_log_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_ship_log_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_smart_alerts" TO "anon";
GRANT ALL ON TABLE "public"."cem_smart_alerts" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_smart_alerts" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategies" TO "anon";
GRANT ALL ON TABLE "public"."cem_strategies" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategies" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategy_blocks" TO "anon";
GRANT ALL ON TABLE "public"."cem_strategy_blocks" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategy_blocks" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategy_combos" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategy_combos" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategy_library" TO "anon";
GRANT ALL ON TABLE "public"."cem_strategy_library" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategy_library" TO "service_role";



GRANT ALL ON TABLE "public"."cem_strategy_optimization" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_strategy_optimization" TO "service_role";



GRANT ALL ON TABLE "public"."cem_thresholds" TO "anon";
GRANT ALL ON TABLE "public"."cem_thresholds" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_thresholds" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_thresholds_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_thresholds_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_thresholds_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_todo" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_todo" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cem_todo_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cem_todo_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cem_todo_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cem_trade_copies" TO "anon";
GRANT ALL ON TABLE "public"."cem_trade_copies" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_trade_copies" TO "service_role";



GRANT ALL ON TABLE "public"."cem_trading_accounts" TO "anon";
GRANT ALL ON TABLE "public"."cem_trading_accounts" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_trading_accounts" TO "service_role";



GRANT ALL ON TABLE "public"."cem_user_library_progress" TO "anon";
GRANT ALL ON TABLE "public"."cem_user_library_progress" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_user_library_progress" TO "service_role";



GRANT ALL ON TABLE "public"."cem_user_memory" TO "anon";
GRANT ALL ON TABLE "public"."cem_user_memory" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_user_memory" TO "service_role";



GRANT ALL ON TABLE "public"."cem_user_profiles" TO "anon";
GRANT ALL ON TABLE "public"."cem_user_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_user_profiles" TO "service_role";



GRANT ALL ON TABLE "public"."cem_user_uploads" TO "anon";
GRANT ALL ON TABLE "public"."cem_user_uploads" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_user_uploads" TO "service_role";



GRANT ALL ON TABLE "public"."cem_users" TO "anon";
GRANT ALL ON TABLE "public"."cem_users" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_users" TO "service_role";



GRANT ALL ON TABLE "public"."cem_weather_trades" TO "anon";
GRANT ALL ON TABLE "public"."cem_weather_trades" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_weather_trades" TO "service_role";



GRANT ALL ON TABLE "public"."cem_weather_bot_performance" TO "anon";
GRANT ALL ON TABLE "public"."cem_weather_bot_performance" TO "authenticated";
GRANT ALL ON TABLE "public"."cem_weather_bot_performance" TO "service_role";



GRANT ALL ON TABLE "public"."conversation_messages" TO "anon";
GRANT ALL ON TABLE "public"."conversation_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."conversation_messages" TO "service_role";



GRANT ALL ON TABLE "public"."conversations" TO "anon";
GRANT ALL ON TABLE "public"."conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."conversations" TO "service_role";



GRANT ALL ON TABLE "public"."file_contents" TO "anon";
GRANT ALL ON TABLE "public"."file_contents" TO "authenticated";
GRANT ALL ON TABLE "public"."file_contents" TO "service_role";



GRANT ALL ON TABLE "public"."files" TO "anon";
GRANT ALL ON TABLE "public"."files" TO "authenticated";
GRANT ALL ON TABLE "public"."files" TO "service_role";



GRANT ALL ON TABLE "public"."files_agents" TO "anon";
GRANT ALL ON TABLE "public"."files_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."files_agents" TO "service_role";



GRANT ALL ON TABLE "public"."groups" TO "anon";
GRANT ALL ON TABLE "public"."groups" TO "authenticated";
GRANT ALL ON TABLE "public"."groups" TO "service_role";



GRANT ALL ON TABLE "public"."groups_agents" TO "anon";
GRANT ALL ON TABLE "public"."groups_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."groups_agents" TO "service_role";



GRANT ALL ON TABLE "public"."groups_blocks" TO "anon";
GRANT ALL ON TABLE "public"."groups_blocks" TO "authenticated";
GRANT ALL ON TABLE "public"."groups_blocks" TO "service_role";



GRANT ALL ON TABLE "public"."identities" TO "anon";
GRANT ALL ON TABLE "public"."identities" TO "authenticated";
GRANT ALL ON TABLE "public"."identities" TO "service_role";



GRANT ALL ON TABLE "public"."identities_agents" TO "anon";
GRANT ALL ON TABLE "public"."identities_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."identities_agents" TO "service_role";



GRANT ALL ON TABLE "public"."identities_blocks" TO "anon";
GRANT ALL ON TABLE "public"."identities_blocks" TO "authenticated";
GRANT ALL ON TABLE "public"."identities_blocks" TO "service_role";



GRANT ALL ON TABLE "public"."jobs" TO "anon";
GRANT ALL ON TABLE "public"."jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."jobs" TO "service_role";



GRANT ALL ON TABLE "public"."llm_batch_items" TO "anon";
GRANT ALL ON TABLE "public"."llm_batch_items" TO "authenticated";
GRANT ALL ON TABLE "public"."llm_batch_items" TO "service_role";



GRANT ALL ON TABLE "public"."llm_batch_job" TO "anon";
GRANT ALL ON TABLE "public"."llm_batch_job" TO "authenticated";
GRANT ALL ON TABLE "public"."llm_batch_job" TO "service_role";



GRANT ALL ON TABLE "public"."mcp_oauth" TO "anon";
GRANT ALL ON TABLE "public"."mcp_oauth" TO "authenticated";
GRANT ALL ON TABLE "public"."mcp_oauth" TO "service_role";



GRANT ALL ON TABLE "public"."mcp_server" TO "anon";
GRANT ALL ON TABLE "public"."mcp_server" TO "authenticated";
GRANT ALL ON TABLE "public"."mcp_server" TO "service_role";



GRANT ALL ON TABLE "public"."mcp_tools" TO "anon";
GRANT ALL ON TABLE "public"."mcp_tools" TO "authenticated";
GRANT ALL ON TABLE "public"."mcp_tools" TO "service_role";



GRANT ALL ON SEQUENCE "public"."messages_sequence_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."messages_sequence_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."messages_sequence_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."messages" TO "anon";
GRANT ALL ON TABLE "public"."messages" TO "authenticated";
GRANT ALL ON TABLE "public"."messages" TO "service_role";



GRANT ALL ON TABLE "public"."orders" TO "anon";
GRANT ALL ON TABLE "public"."orders" TO "authenticated";
GRANT ALL ON TABLE "public"."orders" TO "service_role";



GRANT ALL ON TABLE "public"."organizations" TO "anon";
GRANT ALL ON TABLE "public"."organizations" TO "authenticated";
GRANT ALL ON TABLE "public"."organizations" TO "service_role";



GRANT ALL ON TABLE "public"."passage_tags" TO "anon";
GRANT ALL ON TABLE "public"."passage_tags" TO "authenticated";
GRANT ALL ON TABLE "public"."passage_tags" TO "service_role";



GRANT ALL ON TABLE "public"."prompts" TO "anon";
GRANT ALL ON TABLE "public"."prompts" TO "authenticated";
GRANT ALL ON TABLE "public"."prompts" TO "service_role";



GRANT ALL ON TABLE "public"."provider_models" TO "anon";
GRANT ALL ON TABLE "public"."provider_models" TO "authenticated";
GRANT ALL ON TABLE "public"."provider_models" TO "service_role";



GRANT ALL ON TABLE "public"."provider_trace_metadata" TO "anon";
GRANT ALL ON TABLE "public"."provider_trace_metadata" TO "authenticated";
GRANT ALL ON TABLE "public"."provider_trace_metadata" TO "service_role";



GRANT ALL ON TABLE "public"."provider_traces" TO "anon";
GRANT ALL ON TABLE "public"."provider_traces" TO "authenticated";
GRANT ALL ON TABLE "public"."provider_traces" TO "service_role";



GRANT ALL ON TABLE "public"."providers" TO "anon";
GRANT ALL ON TABLE "public"."providers" TO "authenticated";
GRANT ALL ON TABLE "public"."providers" TO "service_role";



GRANT ALL ON TABLE "public"."run_metrics" TO "anon";
GRANT ALL ON TABLE "public"."run_metrics" TO "authenticated";
GRANT ALL ON TABLE "public"."run_metrics" TO "service_role";



GRANT ALL ON TABLE "public"."runs" TO "anon";
GRANT ALL ON TABLE "public"."runs" TO "authenticated";
GRANT ALL ON TABLE "public"."runs" TO "service_role";



GRANT ALL ON TABLE "public"."sandbox_configs" TO "anon";
GRANT ALL ON TABLE "public"."sandbox_configs" TO "authenticated";
GRANT ALL ON TABLE "public"."sandbox_configs" TO "service_role";



GRANT ALL ON TABLE "public"."sandbox_environment_variables" TO "anon";
GRANT ALL ON TABLE "public"."sandbox_environment_variables" TO "authenticated";
GRANT ALL ON TABLE "public"."sandbox_environment_variables" TO "service_role";



GRANT ALL ON TABLE "public"."source_passages" TO "anon";
GRANT ALL ON TABLE "public"."source_passages" TO "authenticated";
GRANT ALL ON TABLE "public"."source_passages" TO "service_role";



GRANT ALL ON TABLE "public"."sources" TO "anon";
GRANT ALL ON TABLE "public"."sources" TO "authenticated";
GRANT ALL ON TABLE "public"."sources" TO "service_role";



GRANT ALL ON TABLE "public"."sources_agents" TO "anon";
GRANT ALL ON TABLE "public"."sources_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."sources_agents" TO "service_role";



GRANT ALL ON TABLE "public"."step_metrics" TO "anon";
GRANT ALL ON TABLE "public"."step_metrics" TO "authenticated";
GRANT ALL ON TABLE "public"."step_metrics" TO "service_role";



GRANT ALL ON TABLE "public"."steps" TO "anon";
GRANT ALL ON TABLE "public"."steps" TO "authenticated";
GRANT ALL ON TABLE "public"."steps" TO "service_role";



GRANT ALL ON TABLE "public"."tools" TO "anon";
GRANT ALL ON TABLE "public"."tools" TO "authenticated";
GRANT ALL ON TABLE "public"."tools" TO "service_role";



GRANT ALL ON TABLE "public"."tools_agents" TO "anon";
GRANT ALL ON TABLE "public"."tools_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."tools_agents" TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";



GRANT ALL ON TABLE "public"."v_strategy_portfolio" TO "anon";
GRANT ALL ON TABLE "public"."v_strategy_portfolio" TO "authenticated";
GRANT ALL ON TABLE "public"."v_strategy_portfolio" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































