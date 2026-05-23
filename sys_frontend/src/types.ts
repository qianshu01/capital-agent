export interface Entity {
  id: string;
  name: string;
  type: string;
  country: string;
  region: string;
  controlling_family?: string | null;
  controllers?: string[] | null;
  ticker?: string | null;
  exchange?: string | null;
  estimated_aum_usd?: number | null;
  aum_basis?: string | null;
  ownership_pct?: number | null;
  sectors?: string[] | null;
  deployment?: string | null;
  accessibility?: string | null;
  thesis_blurb?: string | null;
  data_quality: number;
  updated_at: string;
}

export interface EntitiesPage { total: number; results: Entity[]; }

export interface AskResponse {
  answer: string;
  entities: Entity[];
  filters_used: Record<string, unknown>;
}

export interface Filters {
  country?: string;
  region?: string;
  type?: string;
  sector?: string;
  min_aum_usd?: number;
  controlling_family?: string;
  q?: string;
  sort?: "aum_desc" | "aum_asc" | "name" | "data_quality_desc";
  limit?: number;
  offset?: number;
}

export interface Evidence {
  question_key: string;
  answer: string;
  confidence: number;
  source_urls: string[];
}

// Replace the previous EntityDetail definition with this one:
export interface EntityDetail {
  entity: Entity;
  sources: { field: string; source_type: string; url?: string | null;
             note?: string | null; retrieved_at: string }[];
  activities: { date?: string | null; kind: string; description: string;
                source_url?: string | null }[];
  assumptions: string[];
  evidence: Evidence[];
}

export type ChatEvent =
  | { event: "tool_call";   data: { tool: string; args: unknown } }
  | { event: "tool_result"; data: { tool: string; summary: string } }
  | { event: "db_write";    data: { entity_id: string } }
  | { event: "message";     data: { text: string } }
  | { event: "error";       data: { message: string } }
  | { event: "done";        data: Record<string, never> };

export interface ChatHistoryMessage { role: string; content: string | null; }
export interface ChatHistory { session_id: string; messages: ChatHistoryMessage[]; }
