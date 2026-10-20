// Generated from schema/research_evidence.py; do not edit by hand.
export type AnswerAddressRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "job_id": string;
};

export type AnswerBlock = {
  "id": string;
  "kind": "fact" | "table" | "relationship" | "documentary" | "limitation";
  "text": string;
  "receipt_ids": (string)[];
  "fact_id"?: (string | null);
  "data"?: (Record<string, unknown> | null);
};

export type AnswerCancelRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "job_id": string;
  "idempotency_key": string;
};

export type AnswerEvent = {
  "cursor": number;
  "job_id": string;
  "elapsed_ms": number;
  "kind": "accepted" | "started" | "progress" | "completed" | "partial" | "cancelled" | "failed" | "unavailable";
  "summary": LocalizedText;
};

export type AnswerEventsRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "job_id": string;
  "after_cursor"?: number;
  "limit"?: number;
};

export type AnswerEventsResponse = {
  "version"?: "research-answers-v1";
  "access_revision": string;
  "job_id": string;
  "binding": ControllerBinding;
  "after_cursor": number;
  "next_cursor": number;
  "latest_event_cursor": number;
  "has_more": boolean;
  "events": (AnswerEvent)[];
};

export type AnswerJob = {
  "id": string;
  "run_id": string;
  "input_version": number;
  "binding": ControllerBinding;
  "locale": "en" | "ja";
  "status": "queued" | "running" | "completed" | "partial" | "cancelled" | "failed" | "unavailable";
  "active_elapsed_ms": number;
  "budget": BudgetSnapshot;
  "event_cursor": 0;
  "latest_event_cursor": number;
  "activity": (Record<string, unknown>)[];
  "answer": (RenderedAnswer | null);
  "error": (LocalizedText | null);
  "synthetic": false;
};

export type AnswerListRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "limit"?: number;
  "cursor"?: (string | null);
};

export type AnswerListResponse = {
  "version"?: "research-answers-v1";
  "access_revision": string;
  "run_id": string;
  "input_version": number;
  "binding": ControllerBinding;
  "eligible": boolean;
  "reason": (LocalizedText | null);
  "items": (AnswerJob)[];
  "next_cursor": (string | null);
};

export type AnswerResponse = {
  "version"?: "research-answers-v1";
  "access_revision": string;
  "job": AnswerJob;
};

export type AnswerSubmitRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "input_version": number;
  "locale"?: "en" | "ja";
  "idempotency_key": string;
};

export type BudgetSnapshot = {
  "active_elapsed_seconds"?: number;
  "tool_actions"?: number;
  "model_calls"?: number;
  "malformed_repairs"?: number;
  "cancellation_requested"?: boolean;
};

export type ContextReference = {
  "kind": "catalogue" | "artifact";
  "id": string;
  "snapshot_id": string;
};

export type ControllerBinding = {
  "investigation_id": string;
  "conversation_id": string;
  "revision_id": string;
  "snapshot_id": string;
  "payload_sha256": string;
};

export type EdnaFilters = {
  "time_from"?: (string | null);
  "time_to"?: (string | null);
  "lat_min"?: (number | null);
  "lat_max"?: (number | null);
  "lon_min"?: (number | null);
  "lon_max"?: (number | null);
  "sample_id"?: (string | null);
  "provider"?: (string | null);
  "provider_project_id"?: (string | null);
  "provider_run_id"?: (string | null);
  "assignment_method"?: ("qcauto_target" | "qcauto_95pct_3nn_target" | null);
  "taxon"?: (string | null);
  "sample_kind"?: ("environmental" | "negative_control" | "positive_control" | "mock_community" | "unknown" | null);
  "is_control"?: (boolean | null);
};

export type EdnaSelection = {
  "enabled": boolean;
  "filters": EdnaFilters;
  "analysis_id"?: (string | null);
};

export type EvidenceAddressRequest = {
  "receipt_id": string;
  "expected_sha256": string;
};

export type EvidenceExportRequest = {
  "receipt_id": string;
  "expected_sha256": string;
  "section"?: "rows" | "inputs";
  "offset"?: number;
  "limit"?: number;
  "format"?: "csv" | "json";
};

export type EvidenceExportResponse = {
  "version"?: "research-evidence-v1";
  "access_revision": string;
  "receipt": EvidenceReceipt;
  "section": "rows" | "inputs";
  "offset": number;
  "returned_count": number;
  "section_total": EvidenceTotal;
  "next_offset": (number | null);
  "format": "csv" | "json";
  "filename": string;
  "mime_type": "text/csv; charset=utf-8" | "application/json; charset=utf-8";
  "content_text": string;
  "content_sha256": string;
  "provenance": Record<string, unknown>;
};

export type EvidenceListRequest = {
  "investigation_id": string;
  "conversation_id": string;
  "run_id": string;
  "input_version": number;
  "offset"?: number;
  "limit"?: number;
};

export type EvidenceListResponse = {
  "version"?: "research-evidence-v1";
  "access_revision": string;
  "run_id": string;
  "input_version": number;
  "offset": number;
  "items": (EvidenceReceipt)[];
  "next_offset": (number | null);
  "total": number;
};

export type EvidencePageRequest = {
  "receipt_id": string;
  "expected_sha256": string;
  "section"?: "rows" | "inputs";
  "offset"?: number;
  "limit"?: number;
};

export type EvidencePageResponse = {
  "version"?: "research-evidence-v1";
  "access_revision": string;
  "receipt": EvidenceReceipt;
  "section": "rows" | "inputs";
  "offset": number;
  "rows": (Record<string, unknown>)[];
  "next_offset": (number | null);
  "section_total": EvidenceTotal;
};

export type EvidenceReceipt = {
  "id": string;
  "sha256": string;
  "run_id": string;
  "input_version": number;
  "binding": ControllerBinding;
  "observation_id": string;
  "kind": "catalogue" | "scientific" | "documentary";
  "authority": "descriptive" | "published" | "experimental" | "documentary";
  "operation_id": (string | null);
  "operation_version": (string | null);
  "parameters": Record<string, unknown>;
  "parameters_sha256": (string | null);
  "scope": EvidenceScope;
  "input_count": number;
  "input_sha256": string;
  "payload_sha256": string;
  "result_content_sha256": (string | null);
  "availability": "available" | "unknown" | "unavailable";
  "source_completeness": "complete" | "partial" | "unknown" | "unavailable";
  "query_completion": "not_started" | "complete" | "partial" | "failed";
  "counts": (SemanticCount)[];
  "total_rows": EvidenceTotal;
  "returned_count": number;
  "offset": number;
  "next_offset": (number | null);
  "preview_rows": (Record<string, unknown>)[];
  "preview_truncated": boolean;
  "columns": (ResultColumn)[];
  "qualifications": (string)[];
  "origin_receipt_ids": (string)[];
  "attachment_reference": ContextReference;
};

export type EvidenceResponse = {
  "version"?: "research-evidence-v1";
  "access_revision": string;
  "receipt": EvidenceReceipt;
};

export type EvidenceScope = {
  "version": 1;
  "sources": SourceSelections;
};

export type EvidenceTotal = {
  "state": "known" | "unknown";
  "value": (number | null);
  "reason": (string | null);
};

export type LocalizedText = {
  "en": string;
  "ja": string;
};

export type RenderedAnswer = {
  "id": string;
  "locale": "en" | "ja";
  "completion": "complete" | "partial";
  "blocks": (AnswerBlock)[];
  "receipt_ids": (string)[];
  "qualifications": (string)[];
  "pack_sha256": string;
  "model_used": boolean;
  "scientific_verification"?: "not_independently_verified";
};

export type ResultColumn = {
  "key": string;
  "title": LocalizedText;
  "unit"?: (string | null);
};

export type SampleFilters = {
  "time_from"?: (string | null);
  "time_to"?: (string | null);
  "bay"?: ("O" | "I" | "M" | null);
  "station"?: (string | null);
  "sample_id"?: (string | null);
};

export type SampleSelection = {
  "enabled": boolean;
  "filters": SampleFilters;
};

export type SatelliteFilters = {
  "time_from"?: (string | null);
  "time_to"?: (string | null);
  "lat_min"?: (number | null);
  "lat_max"?: (number | null);
  "lon_min"?: (number | null);
  "lon_max"?: (number | null);
  "dataset_id"?: (string | null);
};

export type SatelliteSelection = {
  "enabled": boolean;
  "filters": SatelliteFilters;
};

export type SemanticCount = {
  "state": "known" | "unknown";
  "entity": string;
  "denominator": string;
  "value"?: (number | null);
  "reason"?: (string | null);
  "basis"?: "complete_scope";
};

export type SourceSelections = {
  "ctd": SampleSelection;
  "metagenome": SampleSelection;
  "remote_sensing": SatelliteSelection;
  "edna_metabarcoding": EdnaSelection;
};

export type EvidenceModels = {
  "AnswerAddressRequest": AnswerAddressRequest;
  "AnswerBlock": AnswerBlock;
  "AnswerCancelRequest": AnswerCancelRequest;
  "AnswerEvent": AnswerEvent;
  "AnswerEventsRequest": AnswerEventsRequest;
  "AnswerEventsResponse": AnswerEventsResponse;
  "AnswerJob": AnswerJob;
  "AnswerListRequest": AnswerListRequest;
  "AnswerListResponse": AnswerListResponse;
  "AnswerResponse": AnswerResponse;
  "AnswerSubmitRequest": AnswerSubmitRequest;
  "BudgetSnapshot": BudgetSnapshot;
  "ContextReference": ContextReference;
  "ControllerBinding": ControllerBinding;
  "EdnaFilters": EdnaFilters;
  "EdnaSelection": EdnaSelection;
  "EvidenceAddressRequest": EvidenceAddressRequest;
  "EvidenceExportRequest": EvidenceExportRequest;
  "EvidenceExportResponse": EvidenceExportResponse;
  "EvidenceListRequest": EvidenceListRequest;
  "EvidenceListResponse": EvidenceListResponse;
  "EvidencePageRequest": EvidencePageRequest;
  "EvidencePageResponse": EvidencePageResponse;
  "EvidenceReceipt": EvidenceReceipt;
  "EvidenceResponse": EvidenceResponse;
  "EvidenceScope": EvidenceScope;
  "EvidenceTotal": EvidenceTotal;
  "LocalizedText": LocalizedText;
  "RenderedAnswer": RenderedAnswer;
  "ResultColumn": ResultColumn;
  "SampleFilters": SampleFilters;
  "SampleSelection": SampleSelection;
  "SatelliteFilters": SatelliteFilters;
  "SatelliteSelection": SatelliteSelection;
  "SemanticCount": SemanticCount;
  "SourceSelections": SourceSelections;
};
export const evidenceContractSchema = {
  "$defs": {
    "AnswerAddressRequest": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "job_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Job Id",
          "type": "string"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id",
        "job_id"
      ],
      "title": "AnswerAddressRequest",
      "type": "object"
    },
    "AnswerBlock": {
      "additionalProperties": false,
      "properties": {
        "data": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Data"
        },
        "fact_id": {
          "anyOf": [
            {
              "maxLength": 256,
              "minLength": 1,
              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Fact Id"
        },
        "id": {
          "maxLength": 256,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
          "title": "Id",
          "type": "string"
        },
        "kind": {
          "enum": [
            "fact",
            "table",
            "relationship",
            "documentary",
            "limitation"
          ],
          "title": "Kind",
          "type": "string"
        },
        "receipt_ids": {
          "items": {
            "maxLength": 76,
            "minLength": 76,
            "pattern": "^c21:receipt:[a-f0-9]{64}$",
            "type": "string"
          },
          "maxItems": 256,
          "title": "Receipt Ids",
          "type": "array"
        },
        "text": {
          "maxLength": 10000,
          "minLength": 1,
          "title": "Text",
          "type": "string"
        }
      },
      "required": [
        "id",
        "kind",
        "text",
        "receipt_ids"
      ],
      "title": "AnswerBlock",
      "type": "object"
    },
    "AnswerCancelRequest": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "idempotency_key": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Idempotency Key",
          "type": "string"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "job_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Job Id",
          "type": "string"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id",
        "job_id",
        "idempotency_key"
      ],
      "title": "AnswerCancelRequest",
      "type": "object"
    },
    "AnswerEvent": {
      "additionalProperties": false,
      "properties": {
        "cursor": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Cursor",
          "type": "integer"
        },
        "elapsed_ms": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Elapsed Ms",
          "type": "integer"
        },
        "job_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Job Id",
          "type": "string"
        },
        "kind": {
          "enum": [
            "accepted",
            "started",
            "progress",
            "completed",
            "partial",
            "cancelled",
            "failed",
            "unavailable"
          ],
          "title": "Kind",
          "type": "string"
        },
        "summary": {
          "$ref": "#/$defs/LocalizedText"
        }
      },
      "required": [
        "cursor",
        "job_id",
        "elapsed_ms",
        "kind",
        "summary"
      ],
      "title": "AnswerEvent",
      "type": "object"
    },
    "AnswerEventsRequest": {
      "additionalProperties": false,
      "properties": {
        "after_cursor": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "After Cursor",
          "type": "integer"
        },
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "job_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Job Id",
          "type": "string"
        },
        "limit": {
          "default": 100,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id",
        "job_id"
      ],
      "title": "AnswerEventsRequest",
      "type": "object"
    },
    "AnswerEventsResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "after_cursor": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "After Cursor",
          "type": "integer"
        },
        "binding": {
          "$ref": "#/$defs/ControllerBinding"
        },
        "events": {
          "items": {
            "$ref": "#/$defs/AnswerEvent"
          },
          "maxItems": 500,
          "title": "Events",
          "type": "array"
        },
        "has_more": {
          "title": "Has More",
          "type": "boolean"
        },
        "job_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Job Id",
          "type": "string"
        },
        "latest_event_cursor": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Latest Event Cursor",
          "type": "integer"
        },
        "next_cursor": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Next Cursor",
          "type": "integer"
        },
        "version": {
          "const": "research-answers-v1",
          "default": "research-answers-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "job_id",
        "binding",
        "after_cursor",
        "next_cursor",
        "latest_event_cursor",
        "has_more",
        "events"
      ],
      "title": "AnswerEventsResponse",
      "type": "object"
    },
    "AnswerJob": {
      "additionalProperties": false,
      "properties": {
        "active_elapsed_ms": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Active Elapsed Ms",
          "type": "integer"
        },
        "activity": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "maxItems": 0,
          "title": "Activity",
          "type": "array"
        },
        "answer": {
          "anyOf": [
            {
              "$ref": "#/$defs/RenderedAnswer"
            },
            {
              "type": "null"
            }
          ]
        },
        "binding": {
          "$ref": "#/$defs/ControllerBinding"
        },
        "budget": {
          "$ref": "#/$defs/BudgetSnapshot"
        },
        "error": {
          "anyOf": [
            {
              "$ref": "#/$defs/LocalizedText"
            },
            {
              "type": "null"
            }
          ]
        },
        "event_cursor": {
          "const": 0,
          "title": "Event Cursor",
          "type": "integer"
        },
        "id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Id",
          "type": "string"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "latest_event_cursor": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Latest Event Cursor",
          "type": "integer"
        },
        "locale": {
          "enum": [
            "en",
            "ja"
          ],
          "title": "Locale",
          "type": "string"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        },
        "status": {
          "enum": [
            "queued",
            "running",
            "completed",
            "partial",
            "cancelled",
            "failed",
            "unavailable"
          ],
          "title": "Status",
          "type": "string"
        },
        "synthetic": {
          "const": false,
          "title": "Synthetic",
          "type": "boolean"
        }
      },
      "required": [
        "id",
        "run_id",
        "input_version",
        "binding",
        "locale",
        "status",
        "active_elapsed_ms",
        "budget",
        "event_cursor",
        "latest_event_cursor",
        "activity",
        "answer",
        "error",
        "synthetic"
      ],
      "title": "AnswerJob",
      "type": "object"
    },
    "AnswerListRequest": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "cursor": {
          "anyOf": [
            {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Cursor"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "limit": {
          "default": 25,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id"
      ],
      "title": "AnswerListRequest",
      "type": "object"
    },
    "AnswerListResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "binding": {
          "$ref": "#/$defs/ControllerBinding"
        },
        "eligible": {
          "title": "Eligible",
          "type": "boolean"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "items": {
          "items": {
            "$ref": "#/$defs/AnswerJob"
          },
          "maxItems": 500,
          "title": "Items",
          "type": "array"
        },
        "next_cursor": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Cursor"
        },
        "reason": {
          "anyOf": [
            {
              "$ref": "#/$defs/LocalizedText"
            },
            {
              "type": "null"
            }
          ]
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        },
        "version": {
          "const": "research-answers-v1",
          "default": "research-answers-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "run_id",
        "input_version",
        "binding",
        "eligible",
        "reason",
        "items",
        "next_cursor"
      ],
      "title": "AnswerListResponse",
      "type": "object"
    },
    "AnswerResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "job": {
          "$ref": "#/$defs/AnswerJob"
        },
        "version": {
          "const": "research-answers-v1",
          "default": "research-answers-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "job"
      ],
      "title": "AnswerResponse",
      "type": "object"
    },
    "AnswerSubmitRequest": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "idempotency_key": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Idempotency Key",
          "type": "string"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "locale": {
          "default": "en",
          "enum": [
            "en",
            "ja"
          ],
          "title": "Locale",
          "type": "string"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id",
        "input_version",
        "idempotency_key"
      ],
      "title": "AnswerSubmitRequest",
      "type": "object"
    },
    "BudgetSnapshot": {
      "additionalProperties": false,
      "properties": {
        "active_elapsed_seconds": {
          "default": 0.0,
          "minimum": 0,
          "title": "Active Elapsed Seconds",
          "type": "number"
        },
        "cancellation_requested": {
          "default": false,
          "title": "Cancellation Requested",
          "type": "boolean"
        },
        "malformed_repairs": {
          "default": 0,
          "maximum": 1,
          "minimum": 0,
          "title": "Malformed Repairs",
          "type": "integer"
        },
        "model_calls": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Model Calls",
          "type": "integer"
        },
        "tool_actions": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Tool Actions",
          "type": "integer"
        }
      },
      "title": "BudgetSnapshot",
      "type": "object"
    },
    "ContextReference": {
      "additionalProperties": false,
      "properties": {
        "id": {
          "maxLength": 256,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
          "title": "Id",
          "type": "string"
        },
        "kind": {
          "enum": [
            "catalogue",
            "artifact"
          ],
          "title": "Kind",
          "type": "string"
        },
        "snapshot_id": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Snapshot Id",
          "type": "string"
        }
      },
      "required": [
        "kind",
        "id",
        "snapshot_id"
      ],
      "title": "ContextReference",
      "type": "object"
    },
    "ControllerBinding": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "payload_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Payload Sha256",
          "type": "string"
        },
        "revision_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Revision Id",
          "type": "string"
        },
        "snapshot_id": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Snapshot Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "revision_id",
        "snapshot_id",
        "payload_sha256"
      ],
      "title": "ControllerBinding",
      "type": "object"
    },
    "EdnaFilters": {
      "additionalProperties": false,
      "properties": {
        "assignment_method": {
          "anyOf": [
            {
              "enum": [
                "qcauto_target",
                "qcauto_95pct_3nn_target"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Assignment Method"
        },
        "is_control": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Is Control"
        },
        "lat_max": {
          "anyOf": [
            {
              "maximum": 90,
              "minimum": -90,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lat Max"
        },
        "lat_min": {
          "anyOf": [
            {
              "maximum": 90,
              "minimum": -90,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lat Min"
        },
        "lon_max": {
          "anyOf": [
            {
              "maximum": 180,
              "minimum": -180,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lon Max"
        },
        "lon_min": {
          "anyOf": [
            {
              "maximum": 180,
              "minimum": -180,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lon Min"
        },
        "provider": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Provider"
        },
        "provider_project_id": {
          "anyOf": [
            {
              "maxLength": 128,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Provider Project Id"
        },
        "provider_run_id": {
          "anyOf": [
            {
              "maxLength": 128,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Provider Run Id"
        },
        "sample_id": {
          "anyOf": [
            {
              "maxLength": 200,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sample Id"
        },
        "sample_kind": {
          "anyOf": [
            {
              "enum": [
                "environmental",
                "negative_control",
                "positive_control",
                "mock_community",
                "unknown"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sample Kind"
        },
        "taxon": {
          "anyOf": [
            {
              "maxLength": 200,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Taxon"
        },
        "time_from": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time From"
        },
        "time_to": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time To"
        }
      },
      "title": "EdnaFilters",
      "type": "object"
    },
    "EdnaSelection": {
      "additionalProperties": false,
      "properties": {
        "analysis_id": {
          "anyOf": [
            {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Analysis Id"
        },
        "enabled": {
          "title": "Enabled",
          "type": "boolean"
        },
        "filters": {
          "$ref": "#/$defs/EdnaFilters"
        }
      },
      "required": [
        "enabled",
        "filters"
      ],
      "title": "EdnaSelection",
      "type": "object"
    },
    "EvidenceAddressRequest": {
      "additionalProperties": false,
      "properties": {
        "expected_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Expected Sha256",
          "type": "string"
        },
        "receipt_id": {
          "maxLength": 76,
          "minLength": 76,
          "pattern": "^c21:receipt:[a-f0-9]{64}$",
          "title": "Receipt Id",
          "type": "string"
        }
      },
      "required": [
        "receipt_id",
        "expected_sha256"
      ],
      "title": "EvidenceAddressRequest",
      "type": "object"
    },
    "EvidenceExportRequest": {
      "additionalProperties": false,
      "properties": {
        "expected_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Expected Sha256",
          "type": "string"
        },
        "format": {
          "default": "csv",
          "enum": [
            "csv",
            "json"
          ],
          "title": "Format",
          "type": "string"
        },
        "limit": {
          "default": 100,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "offset": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "receipt_id": {
          "maxLength": 76,
          "minLength": 76,
          "pattern": "^c21:receipt:[a-f0-9]{64}$",
          "title": "Receipt Id",
          "type": "string"
        },
        "section": {
          "default": "rows",
          "enum": [
            "rows",
            "inputs"
          ],
          "title": "Section",
          "type": "string"
        }
      },
      "required": [
        "receipt_id",
        "expected_sha256"
      ],
      "title": "EvidenceExportRequest",
      "type": "object"
    },
    "EvidenceExportResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "content_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Content Sha256",
          "type": "string"
        },
        "content_text": {
          "title": "Content Text",
          "type": "string"
        },
        "filename": {
          "maxLength": 200,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9_.-]+$",
          "title": "Filename",
          "type": "string"
        },
        "format": {
          "enum": [
            "csv",
            "json"
          ],
          "title": "Format",
          "type": "string"
        },
        "mime_type": {
          "enum": [
            "text/csv; charset=utf-8",
            "application/json; charset=utf-8"
          ],
          "title": "Mime Type",
          "type": "string"
        },
        "next_offset": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "offset": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "provenance": {
          "additionalProperties": true,
          "title": "Provenance",
          "type": "object"
        },
        "receipt": {
          "$ref": "#/$defs/EvidenceReceipt"
        },
        "returned_count": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Returned Count",
          "type": "integer"
        },
        "section": {
          "enum": [
            "rows",
            "inputs"
          ],
          "title": "Section",
          "type": "string"
        },
        "section_total": {
          "$ref": "#/$defs/EvidenceTotal"
        },
        "version": {
          "const": "research-evidence-v1",
          "default": "research-evidence-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "receipt",
        "section",
        "offset",
        "returned_count",
        "section_total",
        "next_offset",
        "format",
        "filename",
        "mime_type",
        "content_text",
        "content_sha256",
        "provenance"
      ],
      "title": "EvidenceExportResponse",
      "type": "object"
    },
    "EvidenceListRequest": {
      "additionalProperties": false,
      "properties": {
        "conversation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Conversation Id",
          "type": "string"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "investigation_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Investigation Id",
          "type": "string"
        },
        "limit": {
          "default": 100,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "offset": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        }
      },
      "required": [
        "investigation_id",
        "conversation_id",
        "run_id",
        "input_version"
      ],
      "title": "EvidenceListRequest",
      "type": "object"
    },
    "EvidenceListResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "items": {
          "items": {
            "$ref": "#/$defs/EvidenceReceipt"
          },
          "maxItems": 500,
          "title": "Items",
          "type": "array"
        },
        "next_offset": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "offset": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        },
        "total": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Total",
          "type": "integer"
        },
        "version": {
          "const": "research-evidence-v1",
          "default": "research-evidence-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "run_id",
        "input_version",
        "offset",
        "items",
        "next_offset",
        "total"
      ],
      "title": "EvidenceListResponse",
      "type": "object"
    },
    "EvidencePageRequest": {
      "additionalProperties": false,
      "properties": {
        "expected_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Expected Sha256",
          "type": "string"
        },
        "limit": {
          "default": 100,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "offset": {
          "default": 0,
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "receipt_id": {
          "maxLength": 76,
          "minLength": 76,
          "pattern": "^c21:receipt:[a-f0-9]{64}$",
          "title": "Receipt Id",
          "type": "string"
        },
        "section": {
          "default": "rows",
          "enum": [
            "rows",
            "inputs"
          ],
          "title": "Section",
          "type": "string"
        }
      },
      "required": [
        "receipt_id",
        "expected_sha256"
      ],
      "title": "EvidencePageRequest",
      "type": "object"
    },
    "EvidencePageResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "next_offset": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "offset": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "receipt": {
          "$ref": "#/$defs/EvidenceReceipt"
        },
        "rows": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "maxItems": 500,
          "title": "Rows",
          "type": "array"
        },
        "section": {
          "enum": [
            "rows",
            "inputs"
          ],
          "title": "Section",
          "type": "string"
        },
        "section_total": {
          "$ref": "#/$defs/EvidenceTotal"
        },
        "version": {
          "const": "research-evidence-v1",
          "default": "research-evidence-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "receipt",
        "section",
        "offset",
        "rows",
        "next_offset",
        "section_total"
      ],
      "title": "EvidencePageResponse",
      "type": "object"
    },
    "EvidenceReceipt": {
      "additionalProperties": false,
      "properties": {
        "attachment_reference": {
          "$ref": "#/$defs/ContextReference"
        },
        "authority": {
          "enum": [
            "descriptive",
            "published",
            "experimental",
            "documentary"
          ],
          "title": "Authority",
          "type": "string"
        },
        "availability": {
          "enum": [
            "available",
            "unknown",
            "unavailable"
          ],
          "title": "Availability",
          "type": "string"
        },
        "binding": {
          "$ref": "#/$defs/ControllerBinding"
        },
        "columns": {
          "items": {
            "$ref": "#/$defs/ResultColumn"
          },
          "maxItems": 256,
          "title": "Columns",
          "type": "array"
        },
        "counts": {
          "items": {
            "$ref": "#/$defs/SemanticCount"
          },
          "maxItems": 256,
          "title": "Counts",
          "type": "array"
        },
        "id": {
          "maxLength": 76,
          "minLength": 76,
          "pattern": "^c21:receipt:[a-f0-9]{64}$",
          "title": "Id",
          "type": "string"
        },
        "input_count": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Input Count",
          "type": "integer"
        },
        "input_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Input Sha256",
          "type": "string"
        },
        "input_version": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "title": "Input Version",
          "type": "integer"
        },
        "kind": {
          "enum": [
            "catalogue",
            "scientific",
            "documentary"
          ],
          "title": "Kind",
          "type": "string"
        },
        "next_offset": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Next Offset"
        },
        "observation_id": {
          "maxLength": 256,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
          "title": "Observation Id",
          "type": "string"
        },
        "offset": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "operation_id": {
          "anyOf": [
            {
              "maxLength": 256,
              "minLength": 1,
              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Operation Id"
        },
        "operation_version": {
          "anyOf": [
            {
              "maxLength": 256,
              "minLength": 1,
              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Operation Version"
        },
        "origin_receipt_ids": {
          "items": {
            "maxLength": 76,
            "minLength": 76,
            "pattern": "^c21:receipt:[a-f0-9]{64}$",
            "type": "string"
          },
          "maxItems": 256,
          "title": "Origin Receipt Ids",
          "type": "array"
        },
        "parameters": {
          "additionalProperties": true,
          "title": "Parameters",
          "type": "object"
        },
        "parameters_sha256": {
          "anyOf": [
            {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Parameters Sha256"
        },
        "payload_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Payload Sha256",
          "type": "string"
        },
        "preview_rows": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "maxItems": 20,
          "title": "Preview Rows",
          "type": "array"
        },
        "preview_truncated": {
          "title": "Preview Truncated",
          "type": "boolean"
        },
        "qualifications": {
          "items": {
            "maxLength": 10000,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 2048,
          "title": "Qualifications",
          "type": "array"
        },
        "query_completion": {
          "enum": [
            "not_started",
            "complete",
            "partial",
            "failed"
          ],
          "title": "Query Completion",
          "type": "string"
        },
        "result_content_sha256": {
          "anyOf": [
            {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Result Content Sha256"
        },
        "returned_count": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "title": "Returned Count",
          "type": "integer"
        },
        "run_id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Run Id",
          "type": "string"
        },
        "scope": {
          "$ref": "#/$defs/EvidenceScope"
        },
        "sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Sha256",
          "type": "string"
        },
        "source_completeness": {
          "enum": [
            "complete",
            "partial",
            "unknown",
            "unavailable"
          ],
          "title": "Source Completeness",
          "type": "string"
        },
        "total_rows": {
          "$ref": "#/$defs/EvidenceTotal"
        }
      },
      "required": [
        "id",
        "sha256",
        "run_id",
        "input_version",
        "binding",
        "observation_id",
        "kind",
        "authority",
        "operation_id",
        "operation_version",
        "parameters",
        "parameters_sha256",
        "scope",
        "input_count",
        "input_sha256",
        "payload_sha256",
        "result_content_sha256",
        "availability",
        "source_completeness",
        "query_completion",
        "counts",
        "total_rows",
        "returned_count",
        "offset",
        "next_offset",
        "preview_rows",
        "preview_truncated",
        "columns",
        "qualifications",
        "origin_receipt_ids",
        "attachment_reference"
      ],
      "title": "EvidenceReceipt",
      "type": "object"
    },
    "EvidenceResponse": {
      "additionalProperties": false,
      "properties": {
        "access_revision": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Access Revision",
          "type": "string"
        },
        "receipt": {
          "$ref": "#/$defs/EvidenceReceipt"
        },
        "version": {
          "const": "research-evidence-v1",
          "default": "research-evidence-v1",
          "title": "Version",
          "type": "string"
        }
      },
      "required": [
        "access_revision",
        "receipt"
      ],
      "title": "EvidenceResponse",
      "type": "object"
    },
    "EvidenceScope": {
      "additionalProperties": false,
      "properties": {
        "sources": {
          "$ref": "#/$defs/SourceSelections"
        },
        "version": {
          "const": 1,
          "title": "Version",
          "type": "integer"
        }
      },
      "required": [
        "version",
        "sources"
      ],
      "title": "EvidenceScope",
      "type": "object"
    },
    "EvidenceTotal": {
      "additionalProperties": false,
      "properties": {
        "reason": {
          "anyOf": [
            {
              "maxLength": 10000,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Reason"
        },
        "state": {
          "enum": [
            "known",
            "unknown"
          ],
          "title": "State",
          "type": "string"
        },
        "value": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "title": "Value"
        }
      },
      "required": [
        "state",
        "value",
        "reason"
      ],
      "title": "EvidenceTotal",
      "type": "object"
    },
    "LocalizedText": {
      "additionalProperties": false,
      "properties": {
        "en": {
          "maxLength": 4000,
          "minLength": 1,
          "pattern": "\\S",
          "title": "En",
          "type": "string"
        },
        "ja": {
          "maxLength": 4000,
          "minLength": 1,
          "pattern": "\\S",
          "title": "Ja",
          "type": "string"
        }
      },
      "required": [
        "en",
        "ja"
      ],
      "title": "LocalizedText",
      "type": "object"
    },
    "RenderedAnswer": {
      "additionalProperties": false,
      "properties": {
        "blocks": {
          "items": {
            "$ref": "#/$defs/AnswerBlock"
          },
          "maxItems": 512,
          "title": "Blocks",
          "type": "array"
        },
        "completion": {
          "enum": [
            "complete",
            "partial"
          ],
          "title": "Completion",
          "type": "string"
        },
        "id": {
          "maxLength": 36,
          "minLength": 36,
          "pattern": "^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
          "title": "Id",
          "type": "string"
        },
        "locale": {
          "enum": [
            "en",
            "ja"
          ],
          "title": "Locale",
          "type": "string"
        },
        "model_used": {
          "title": "Model Used",
          "type": "boolean"
        },
        "pack_sha256": {
          "pattern": "^[a-f0-9]{64}$",
          "title": "Pack Sha256",
          "type": "string"
        },
        "qualifications": {
          "items": {
            "maxLength": 10000,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 2048,
          "title": "Qualifications",
          "type": "array"
        },
        "receipt_ids": {
          "items": {
            "maxLength": 76,
            "minLength": 76,
            "pattern": "^c21:receipt:[a-f0-9]{64}$",
            "type": "string"
          },
          "maxItems": 1024,
          "title": "Receipt Ids",
          "type": "array"
        },
        "scientific_verification": {
          "const": "not_independently_verified",
          "default": "not_independently_verified",
          "title": "Scientific Verification",
          "type": "string"
        }
      },
      "required": [
        "id",
        "locale",
        "completion",
        "blocks",
        "receipt_ids",
        "qualifications",
        "pack_sha256",
        "model_used"
      ],
      "title": "RenderedAnswer",
      "type": "object"
    },
    "ResultColumn": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "maxLength": 256,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
          "title": "Key",
          "type": "string"
        },
        "title": {
          "$ref": "#/$defs/LocalizedText"
        },
        "unit": {
          "anyOf": [
            {
              "maxLength": 4000,
              "minLength": 1,
              "pattern": "\\S",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Unit"
        }
      },
      "required": [
        "key",
        "title"
      ],
      "title": "ResultColumn",
      "type": "object"
    },
    "SampleFilters": {
      "additionalProperties": false,
      "properties": {
        "bay": {
          "anyOf": [
            {
              "enum": [
                "O",
                "I",
                "M"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Bay"
        },
        "sample_id": {
          "anyOf": [
            {
              "maxLength": 200,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Sample Id"
        },
        "station": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Station"
        },
        "time_from": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time From"
        },
        "time_to": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time To"
        }
      },
      "title": "SampleFilters",
      "type": "object"
    },
    "SampleSelection": {
      "additionalProperties": false,
      "properties": {
        "enabled": {
          "title": "Enabled",
          "type": "boolean"
        },
        "filters": {
          "$ref": "#/$defs/SampleFilters"
        }
      },
      "required": [
        "enabled",
        "filters"
      ],
      "title": "SampleSelection",
      "type": "object"
    },
    "SatelliteFilters": {
      "additionalProperties": false,
      "properties": {
        "dataset_id": {
          "anyOf": [
            {
              "maxLength": 128,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Dataset Id"
        },
        "lat_max": {
          "anyOf": [
            {
              "maximum": 90,
              "minimum": -90,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lat Max"
        },
        "lat_min": {
          "anyOf": [
            {
              "maximum": 90,
              "minimum": -90,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lat Min"
        },
        "lon_max": {
          "anyOf": [
            {
              "maximum": 180,
              "minimum": -180,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lon Max"
        },
        "lon_min": {
          "anyOf": [
            {
              "maximum": 180,
              "minimum": -180,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Lon Min"
        },
        "time_from": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time From"
        },
        "time_to": {
          "anyOf": [
            {
              "maxLength": 64,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Time To"
        }
      },
      "title": "SatelliteFilters",
      "type": "object"
    },
    "SatelliteSelection": {
      "additionalProperties": false,
      "properties": {
        "enabled": {
          "title": "Enabled",
          "type": "boolean"
        },
        "filters": {
          "$ref": "#/$defs/SatelliteFilters"
        }
      },
      "required": [
        "enabled",
        "filters"
      ],
      "title": "SatelliteSelection",
      "type": "object"
    },
    "SemanticCount": {
      "additionalProperties": false,
      "properties": {
        "basis": {
          "const": "complete_scope",
          "default": "complete_scope",
          "title": "Basis",
          "type": "string"
        },
        "denominator": {
          "maxLength": 10000,
          "minLength": 1,
          "title": "Denominator",
          "type": "string"
        },
        "entity": {
          "maxLength": 256,
          "minLength": 1,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
          "title": "Entity",
          "type": "string"
        },
        "reason": {
          "anyOf": [
            {
              "maxLength": 10000,
              "minLength": 1,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Reason"
        },
        "state": {
          "enum": [
            "known",
            "unknown"
          ],
          "title": "State",
          "type": "string"
        },
        "value": {
          "anyOf": [
            {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Value"
        }
      },
      "required": [
        "state",
        "entity",
        "denominator"
      ],
      "title": "SemanticCount",
      "type": "object"
    },
    "SourceSelections": {
      "additionalProperties": false,
      "properties": {
        "ctd": {
          "$ref": "#/$defs/SampleSelection"
        },
        "edna_metabarcoding": {
          "$ref": "#/$defs/EdnaSelection"
        },
        "metagenome": {
          "$ref": "#/$defs/SampleSelection"
        },
        "remote_sensing": {
          "$ref": "#/$defs/SatelliteSelection"
        }
      },
      "required": [
        "ctd",
        "metagenome",
        "remote_sensing",
        "edna_metabarcoding"
      ],
      "title": "SourceSelections",
      "type": "object"
    }
  }
} as const;
