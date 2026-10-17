// Generated from contracts/openapi.json by `npm run api:gen`. Do not edit.
export interface paths {
    "/api/v1/assertion-relations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Relation */
        post: operations["create_relation_api_v1_assertion_relations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assertions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Assertions */
        get: operations["list_assertions_api_v1_assertions_get"];
        put?: never;
        /** Create Assertion */
        post: operations["create_assertion_api_v1_assertions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assertions/{assertion_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Assertion */
        get: operations["get_assertion_api_v1_assertions__assertion_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/assertions/{assertion_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Assertion */
        post: operations["revise_assertion_api_v1_assertions__assertion_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/book-versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version */
        get: operations["get_version_api_v1_book_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/book-versions/{version_id}/pages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pages */
        get: operations["list_pages_api_v1_book_versions__version_id__pages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/book-versions/{version_id}/process": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Process Version */
        post: operations["process_version_api_v1_book_versions__version_id__process_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/book-versions/{version_id}/school-scopes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Scopes */
        get: operations["list_scopes_api_v1_book_versions__version_id__school_scopes_get"];
        put?: never;
        /** Create Scope */
        post: operations["create_scope_api_v1_book_versions__version_id__school_scopes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/book-versions/{version_id}/withdraw": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Withdraw
         * @description Synchronous: visibility is revoked when this returns (idempotent).
         */
        post: operations["withdraw_api_v1_book_versions__version_id__withdraw_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/books": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Books */
        get: operations["list_books_api_v1_books_get"];
        put?: never;
        /** Create Book */
        post: operations["create_book_api_v1_books_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/books/{book_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Book */
        get: operations["get_book_api_v1_books__book_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Book */
        patch: operations["patch_book_api_v1_books__book_id__patch"];
        trace?: never;
    };
    "/api/v1/books/{book_id}/access": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Access */
        get: operations["get_access_api_v1_books__book_id__access_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Put Access */
        patch: operations["put_access_api_v1_books__book_id__access_patch"];
        trace?: never;
    };
    "/api/v1/books/{book_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Versions */
        get: operations["versions_api_v1_books__book_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Cases */
        get: operations["list_cases_api_v1_cases_get"];
        put?: never;
        /** Create Case */
        post: operations["create_case_api_v1_cases_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Case */
        get: operations["get_case_api_v1_cases__case_id__get"];
        put?: never;
        post?: never;
        /** Delete Case */
        delete: operations["delete_case_api_v1_cases__case_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Case */
        post: operations["revise_case_api_v1_cases__case_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/citations/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve Citations
         * @description Invalid citations must never reach a reader, not even in a streaming draft.
         */
        post: operations["resolve_citations_api_v1_citations_resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/concepts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Concepts */
        get: operations["list_concepts_api_v1_concepts_get"];
        put?: never;
        /** Create Concept */
        post: operations["create_concept_api_v1_concepts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/concepts/{concept_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Concept */
        get: operations["get_concept_api_v1_concepts__concept_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/concepts/{concept_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Concept */
        post: operations["revise_concept_api_v1_concepts__concept_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/corpus-releases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Releases */
        get: operations["list_releases_api_v1_corpus_releases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/corpus-releases/{release_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Release */
        get: operations["get_release_api_v1_corpus_releases__release_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/corpus-releases/{release_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activate */
        post: operations["activate_api_v1_corpus_releases__release_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evaluation-datasets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Datasets */
        get: operations["list_datasets_api_v1_evaluation_datasets_get"];
        put?: never;
        /** Create Dataset */
        post: operations["create_dataset_api_v1_evaluation_datasets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evaluation-datasets/{dataset_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Dataset */
        post: operations["approve_dataset_api_v1_evaluation_datasets__dataset_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evaluation-datasets/{dataset_id}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Items */
        get: operations["list_items_api_v1_evaluation_datasets__dataset_id__items_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evaluation-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Run */
        post: operations["create_run_api_v1_evaluation_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evaluation-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Run */
        get: operations["get_run_api_v1_evaluation_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Evidence */
        post: operations["create_evidence_api_v1_evidence_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evidence/{evidence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Evidence */
        get: operations["get_evidence_api_v1_evidence__evidence_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/{generation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Generation */
        get: operations["get_generation_api_v1_generations__generation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/{generation_id}/impact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation Impact */
        get: operations["generation_impact_api_v1_generations__generation_id__impact_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/{generation_id}/publish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Publish */
        post: operations["publish_api_v1_generations__generation_id__publish_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Live
         * @description Process is up. No dependency calls, versions or configuration.
         */
        get: operations["live_api_v1_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["ready_api_v1_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ingestion-batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** New Batch */
        post: operations["new_batch_api_v1_ingestion_batches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ingestion-batches/{batch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Batch */
        get: operations["get_batch_api_v1_ingestion_batches__batch_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Jobs */
        get: operations["list_jobs_api_v1_jobs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job */
        get: operations["get_job_api_v1_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Job */
        post: operations["cancel_job_api_v1_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Job Events */
        get: operations["job_events_api_v1_jobs__job_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Job */
        post: operations["retry_job_api_v1_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/impact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Knowledge Impact */
        get: operations["knowledge_impact_api_v1_knowledge_impact_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/methods": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Methods */
        get: operations["list_methods_api_v1_methods_get"];
        put?: never;
        /** Create Method */
        post: operations["create_method_api_v1_methods_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/methods/{method_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Method */
        get: operations["get_method_api_v1_methods__method_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/methods/{method_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Method */
        post: operations["revise_method_api_v1_methods__method_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/model-profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Profiles */
        get: operations["list_profiles_api_v1_model_profiles_get"];
        put?: never;
        /** Create Profile */
        post: operations["create_profile_api_v1_model_profiles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/model-profiles/{profile_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activate */
        post: operations["activate_api_v1_model_profiles__profile_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/model-profiles/{profile_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Test Profile */
        post: operations["test_profile_api_v1_model_profiles__profile_id__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ontology-releases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Releases */
        get: operations["list_releases_api_v1_ontology_releases_get"];
        put?: never;
        /** Publish */
        post: operations["publish_api_v1_ontology_releases_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ontology-releases/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preview */
        get: operations["preview_api_v1_ontology_releases_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ontology-releases/{release_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Release */
        get: operations["get_release_api_v1_ontology_releases__release_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/page-revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Revision */
        get: operations["get_revision_api_v1_page_revisions__revision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/page-revisions/{revision_id}/render": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Render Page
         * @description The page image a reviewer compares with the text (docs/11 · /review/ocr).
         */
        get: operations["render_page_api_v1_page_revisions__revision_id__render_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pages/{page_id}/corrections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Correct Page */
        post: operations["correct_page_api_v1_pages__page_id__corrections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline-profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Pipeline Profiles
         * @description Newest first; the UI preselects the newest profile whose collection is ready.
         */
        get: operations["pipeline_profiles_api_v1_pipeline_profiles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Items */
        get: operations["list_items_api_v1_review_items_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-items/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Item */
        get: operations["get_item_api_v1_review_items__item_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-items/{item_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve */
        post: operations["resolve_api_v1_review_items__item_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Review */
        post: operations["review_api_v1_reviews_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Rules */
        get: operations["list_rules_api_v1_rules_get"];
        put?: never;
        /** Create Rule */
        post: operations["create_rule_api_v1_rules_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rules/{rule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Rule */
        get: operations["get_rule_api_v1_rules__rule_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rules/{rule_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Rule */
        post: operations["revise_rule_api_v1_rules__rule_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rules/{rule_id}/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate Rule */
        post: operations["validate_rule_api_v1_rules__rule_id__validate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/schools": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Schools */
        get: operations["list_schools_api_v1_schools_get"];
        put?: never;
        /** Create School */
        post: operations["create_school_api_v1_schools_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/schools/{school_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get School */
        get: operations["get_school_api_v1_schools__school_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Search */
        post: operations["run_search_api_v1_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Settings */
        get: operations["get_settings_api_v1_settings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Setting */
        patch: operations["patch_setting_api_v1_settings_patch"];
        trace?: never;
    };
    "/api/v1/terms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search Terms */
        get: operations["search_terms_api_v1_terms_get"];
        put?: never;
        /** Create Term */
        post: operations["create_term_api_v1_terms_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/terms/{term_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Term */
        get: operations["get_term_api_v1_terms__term_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/topics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Topics */
        get: operations["list_topics_api_v1_topics_get"];
        put?: never;
        /** Create Topic */
        post: operations["create_topic_api_v1_topics_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/uploads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload */
        post: operations["upload_api_v1_uploads_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usage */
        get: operations["usage_api_v1_usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Users */
        get: operations["users_api_v1_users_get"];
        put?: never;
        /** Create */
        post: operations["create_api_v1_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User */
        get: operations["get_user_api_v1_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch */
        patch: operations["patch_api_v1_users__user_id__patch"];
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AccessInput */
        AccessInput: {
            /** Grants */
            grants: components["schemas"]["Grant"][];
        };
        /** ActivateInput */
        ActivateInput: {
            /**
             * Expected Active Id
             * @description the release the caller saw active (null for an empty corpus)
             */
            expected_active_id: string | null;
        };
        /** ActiveCoverage */
        ActiveCoverage: {
            /** Accepted */
            accepted: number;
            /** Excluded */
            excluded: number;
            /** Review Required */
            review_required: number;
            /** Total */
            total: number;
            /** Versions */
            versions: number;
        };
        /** ActivePointer */
        ActivePointer: {
            /**
             * Release Id
             * Format: uuid
             */
            release_id: string;
            /** Visibility Epoch */
            visibility_epoch: number;
        };
        /** AssertionDTO */
        AssertionDTO: {
            /** Applicability */
            applicability: {
                [key: string]: unknown;
            };
            /** Assertion Key */
            assertion_key: string;
            /**
             * Author Id
             * Format: uuid
             */
            author_id: string;
            /** Concept Id */
            concept_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Exception Text */
            exception_text: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Method Id */
            method_id: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /** Revision */
            revision: number;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /** Statement */
            statement: string;
        };
        /** AssertionDetail */
        AssertionDetail: {
            /** Applicability */
            applicability: {
                [key: string]: unknown;
            };
            /** Assertion Key */
            assertion_key: string;
            /**
             * Author Id
             * Format: uuid
             */
            author_id: string;
            /** Concept Id */
            concept_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Exception Text */
            exception_text: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Method Id */
            method_id: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /** Relations */
            relations: components["schemas"]["RelationDTO"][];
            /** Revision */
            revision: number;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /** Sources */
            sources: components["schemas"]["SourceDTO"][];
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /** Statement */
            statement: string;
        };
        /** AssertionInput */
        AssertionInput: {
            /** Applicability */
            applicability?: {
                [key: string]: unknown;
            };
            /** Assertion Key */
            assertion_key?: string | null;
            /** Concept Id */
            concept_id?: string | null;
            /** Evidence Ids */
            evidence_ids: string[];
            /** Exception Text */
            exception_text?: string | null;
            /** Method Id */
            method_id?: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** Statement */
            statement: string;
        };
        /** AssertionRevisionInput */
        AssertionRevisionInput: {
            /** Applicability */
            applicability?: {
                [key: string]: unknown;
            } | null;
            /** Base Revision */
            base_revision: number;
            /** Concept Id */
            concept_id?: string | null;
            /** Evidence Ids */
            evidence_ids?: string[] | null;
            /** Exception Text */
            exception_text?: string | null;
            /** Method Id */
            method_id?: string | null;
            /** Origin */
            origin?: ("source_explicit" | "editor_interpretation" | "ai_inferred") | null;
            /** Reason */
            reason: string;
            /** Statement */
            statement?: string | null;
        };
        /** AuthorInput */
        AuthorInput: {
            /** Name */
            name: string;
            /**
             * Role
             * @default author
             * @enum {string}
             */
            role: "author" | "commentator" | "translator" | "editor";
        };
        /** AuthorRef */
        AuthorRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Role */
            role: string;
        };
        /** BatchDTO */
        BatchDTO: {
            /** Auto Publish */
            auto_publish: boolean;
            /** Counters */
            counters: {
                [key: string]: number;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Items */
            items: components["schemas"]["BatchItem"][];
            /** Name */
            name: string;
            /** Pipeline Profile Id */
            pipeline_profile_id: string | null;
            /** State */
            state: string;
        };
        /** BatchInput */
        BatchInput: {
            /**
             * Auto Publish
             * @default false
             */
            auto_publish: boolean;
            /** Name */
            name: string;
            /** Pipeline Profile Id */
            pipeline_profile_id?: string | null;
        };
        /** BatchItem */
        BatchItem: {
            /** Display Name */
            display_name: string;
            /** Duplicate Of */
            duplicate_of: string | null;
            /** Error Code */
            error_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Job Id */
            job_id: string | null;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "accepted" | "duplicate" | "rejected";
            /** Sha256 */
            sha256: string | null;
            /** Size Bytes */
            size_bytes: number | null;
            /** Version Id */
            version_id: string | null;
        };
        /** BlockChange */
        BlockChange: {
            /** Kind */
            kind?: ("paragraph" | "heading" | "table" | "figure" | "caption") | null;
            /** Level */
            level?: number | null;
            /** Ordinal */
            ordinal: number;
            /**
             * Role
             * @description body removes the page-furniture role
             */
            role?: ("body" | "header" | "footer" | "folio" | "toc") | null;
            /** Speaker Layer */
            speaker_layer?: ("original_author" | "commentator" | "translator" | "editor" | "unknown") | null;
            /** Table Cells */
            table_cells?: string[][] | null;
            /** Text */
            text?: string | null;
        };
        /** BlockDTO */
        BlockDTO: {
            /** Attributes */
            attributes: {
                [key: string]: unknown;
            };
            /** Bbox */
            bbox: number[];
            /** End Offset */
            end_offset: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "paragraph" | "heading" | "table" | "figure" | "caption";
            /** Ordinal */
            ordinal: number;
            /**
             * Speaker Layer
             * @enum {string}
             */
            speaker_layer: "original_author" | "commentator" | "translator" | "editor" | "unknown";
            /** Start Offset */
            start_offset: number;
            /** Table Cells */
            table_cells: string[][] | null;
            /** Text */
            text: string;
        };
        /** Body_upload_api_v1_uploads_post */
        Body_upload_api_v1_uploads_post: {
            /**
             * Batch Id
             * Format: uuid
             */
            batch_id: string;
            /** Book Id */
            book_id?: string | null;
            /**
             * Edition Label
             * @default v1
             */
            edition_label: string;
            /**
             * External Processing Allowed
             * @default false
             */
            external_processing_allowed: boolean;
            /** File */
            file: string;
            /**
             * Language
             * @default vi
             */
            language: string;
            /**
             * Rights Status
             * @enum {string}
             */
            rights_status: "unknown" | "private_reference" | "licensed" | "public_domain" | "restricted";
            /** Title */
            title?: string | null;
        };
        /** BookDTO */
        BookDTO: {
            /** @description pages of the book's versions in the active corpus release; null if none */
            active_coverage: components["schemas"]["ActiveCoverage"] | null;
            /** Authors */
            authors: components["schemas"]["AuthorRef"][];
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Language */
            language: string;
            /** Revision */
            revision: number;
            /** Title */
            title: string;
            /** Versions Count */
            versions_count: number;
        };
        /** BookInput */
        BookInput: {
            /**
             * Authors
             * @default []
             */
            authors: components["schemas"]["AuthorInput"][];
            /** Description */
            description?: string | null;
            /**
             * Language
             * @default vi
             */
            language: string;
            /** Title */
            title: string;
        };
        /** BookPatch */
        BookPatch: {
            /** Description */
            description?: string | null;
            /** Language */
            language?: string | null;
            /** Title */
            title?: string | null;
        };
        /** BudgetRow */
        BudgetRow: {
            /** Currency */
            currency: string;
            /** Daily Budget */
            daily_budget: number;
            /**
             * Profile Id
             * Format: uuid
             */
            profile_id: string;
            /** Spent Today */
            spent_today: number;
        };
        /** Bundle */
        Bundle: {
            /**
             * Bundle Id
             * Format: uuid
             * @description cite its handles via POST /citations/resolve
             */
            bundle_id: string;
            /** Groups */
            groups: components["schemas"]["EvidenceGroup"][];
            /** Omitted */
            omitted: number;
            /** Tokens */
            tokens: number;
            /** Truncated */
            truncated: boolean;
        };
        /** BundleSpan */
        BundleSpan: {
            /**
             * Block Id
             * Format: uuid
             */
            block_id: string;
            /** End Offset */
            end_offset: number;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Start Offset */
            start_offset: number;
        };
        /** CaseDTO */
        CaseDTO: {
            /** Case Key */
            case_key: string;
            /**
             * Chart Payload
             * @description book-case/1: pillars, sex_for_luck, luck_pillars
             */
            chart_payload: {
                [key: string]: unknown;
            };
            /**
             * Claimed Events
             * @description the source's account, not verified outcomes
             */
            claimed_events: unknown[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Method Id */
            method_id: string | null;
            /** Narrative */
            narrative: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "book_case" | "user_case" | "synthetic_test";
            /** Owner Id */
            owner_id: string | null;
            /** Quality */
            quality: {
                [key: string]: unknown;
            };
            /** Revision */
            revision: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /**
             * Visibility
             * @enum {string}
             */
            visibility: "private" | "library";
        };
        /** CaseDetail */
        CaseDetail: {
            /** Case Key */
            case_key: string;
            /**
             * Chart Payload
             * @description book-case/1: pillars, sex_for_luck, luck_pillars
             */
            chart_payload: {
                [key: string]: unknown;
            };
            /**
             * Claimed Events
             * @description the source's account, not verified outcomes
             */
            claimed_events: unknown[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Method Id */
            method_id: string | null;
            /** Narrative */
            narrative: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "book_case" | "user_case" | "synthetic_test";
            /** Owner Id */
            owner_id: string | null;
            /** Quality */
            quality: {
                [key: string]: unknown;
            };
            /** Revision */
            revision: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Revisions */
            revisions: components["schemas"]["CaseRevisionRef"][];
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /** Sources */
            sources: components["schemas"]["CaseSource"][];
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /**
             * Visibility
             * @enum {string}
             */
            visibility: "private" | "library";
        };
        /** CaseInput */
        CaseInput: {
            /** Case Key */
            case_key?: string | null;
            /** Chart Payload */
            chart_payload: {
                [key: string]: unknown;
            };
            /**
             * Claimed Events
             * @default []
             */
            claimed_events: unknown[];
            /**
             * Evidence Ids
             * @default []
             */
            evidence_ids: string[];
            /** Method Id */
            method_id?: string | null;
            /**
             * Narrative
             * @default
             */
            narrative: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "book_case" | "user_case" | "synthetic_test";
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
        };
        /** CaseRevisionInput */
        CaseRevisionInput: {
            /** Base Revision */
            base_revision: number;
            /** Chart Payload */
            chart_payload?: {
                [key: string]: unknown;
            } | null;
            /** Claimed Events */
            claimed_events?: unknown[] | null;
            /** Evidence Ids */
            evidence_ids?: string[] | null;
            /** Method Id */
            method_id?: string | null;
            /** Narrative */
            narrative?: string | null;
            /** Reason */
            reason: string;
            /** School Id */
            school_id?: string | null;
        };
        /** CaseRevisionRef */
        CaseRevisionRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** CaseSource */
        CaseSource: {
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Evidence Id
             * Format: uuid
             */
            evidence_id: string;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Quote */
            quote: string;
        };
        /** Changes */
        Changes: {
            /** Added */
            added: string[];
            /** Removed */
            removed: string[];
            /** Total */
            total: number;
        };
        /** CheckDTO */
        CheckDTO: {
            /** Code */
            code: string;
            /** Essential */
            essential: boolean;
            /** Name */
            name: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "degraded" | "fail";
        };
        /** Citation */
        Citation: {
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Book Title */
            book_title: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** Edition Label */
            edition_label: string;
            /** Evidence Id */
            evidence_id: string;
            /** Evidence Span Ids */
            evidence_span_ids: string[];
            /** Pages */
            pages: number[];
            /** Printed Pages */
            printed_pages: string[];
            /** Quote */
            quote: string;
            /** Section Title */
            section_title: string;
            /** Speaker Layer */
            speaker_layer: string;
            /**
             * Support
             * @description share of the claim content words in the cited text
             */
            support: number;
            /** Viewer */
            viewer: components["schemas"]["ViewerSpan"][];
        };
        /** ClaimInput */
        ClaimInput: {
            /**
             * Evidence Ids
             * @description handles from the bundle (E1…)
             */
            evidence_ids: string[];
            /** Quote */
            quote?: string | null;
            /** Text */
            text: string;
        };
        /** ClaimResult */
        ClaimResult: {
            /** Citations */
            citations: components["schemas"]["Citation"][];
            /** Index */
            index: number;
            /** Problems */
            problems: components["schemas"]["backend__app__api__search__Problem"][];
            /**
             * Status
             * @enum {string}
             */
            status: "supported" | "weak" | "insufficient_evidence" | "invalid";
            /** Support */
            support: number;
        };
        /** ConceptDTO */
        ConceptDTO: {
            /** Canonical Key */
            canonical_key: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string;
            /** Revision */
            revision: number;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** ConceptDetail */
        ConceptDetail: {
            /** Canonical Key */
            canonical_key: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string;
            /** Reviews */
            reviews: components["schemas"]["ReviewRecord"][];
            /** Revision */
            revision: number;
            /** Revisions */
            revisions: components["schemas"]["backend__app__api__knowledge__RevisionRef"][];
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /** Terms */
            terms: components["schemas"]["TermDTO"][];
        };
        /** ConceptInput */
        ConceptInput: {
            /** Canonical Key */
            canonical_key: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Han
             * @description chữ Hán, a zh alias
             */
            han?: string | null;
            /** Label */
            label: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
        };
        /** ConceptRef */
        ConceptRef: {
            /** Canonical Key */
            canonical_key: string;
            /** Label */
            label: string;
            /** Revision */
            revision: number;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** ConceptRevisionInput */
        ConceptRevisionInput: {
            /** Base Revision */
            base_revision: number;
            /** Description */
            description?: string | null;
            /** Label */
            label?: string | null;
            /** Reason */
            reason: string;
        };
        /** CorrectionInput */
        CorrectionInput: {
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Changes */
            changes: components["schemas"]["BlockChange"][];
            /** Reason */
            reason: string;
        };
        /** CorrectionResult */
        CorrectionResult: {
            /** Changed Blocks */
            changed_blocks: number[];
            /**
             * Coalesced
             * @description joined a rebuild that was still queued
             */
            coalesced: boolean;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            revision: components["schemas"]["backend__app__api__pages__RevisionRef"];
            source_changed: components["schemas"]["SourceChanged"];
        };
        /** Coverage */
        Coverage: {
            /** Accepted */
            accepted: number;
            /** Excluded */
            excluded: number;
            /** Failed */
            failed: number;
            /** Total */
            total: number;
        };
        /** DatasetDTO */
        DatasetDTO: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Items */
            items: number;
            /** Name */
            name: string;
            /** Rights */
            rights: {
                [key: string]: unknown;
            };
            /** Split Manifest */
            split_manifest: {
                [key: string]: unknown;
            };
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "approved" | "retired";
            /** Version */
            version: string;
        };
        /** DatasetInput */
        DatasetInput: {
            /** Items */
            items: components["schemas"]["DatasetItem"][];
            /** Name */
            name: string;
            /** Rights */
            rights?: {
                [key: string]: unknown;
            };
            /** Version */
            version: string;
        };
        /** DatasetItem */
        DatasetItem: {
            expected: components["schemas"]["ItemExpected"];
            input: components["schemas"]["ItemInput"];
            /** Key */
            key: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "retrieval" | "no_answer";
            /** Source Manifest */
            source_manifest?: {
                [key: string]: unknown;
            };
            /**
             * Split
             * @default dev
             * @enum {string}
             */
            split: "dev" | "test" | "holdout";
        };
        /** Dependents */
        Dependents: {
            /** Analyses */
            analyses: number;
            /** Runs */
            runs: number;
        };
        /** DslProblem */
        DslProblem: {
            /** Message */
            message: string;
            /** Path */
            path: string;
        };
        /** EmbeddingRef */
        EmbeddingRef: {
            /** Dimension */
            dimension: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Locality
             * @description external: book text leaves the server only for versions that allow it
             * @enum {string}
             */
            locality: "fixture" | "local" | "external";
            /** Model Name */
            model_name: string;
            /** Model Revision */
            model_revision: string;
            /** Provider */
            provider: string;
            /**
             * Ready
             * @description its vector collection is provisioned
             */
            ready: boolean;
        };
        /** Envelope[AssertionDetail] */
        Envelope_AssertionDetail_: {
            data: components["schemas"]["AssertionDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[BatchDTO] */
        Envelope_BatchDTO_: {
            data: components["schemas"]["BatchDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[BookDTO] */
        Envelope_BookDTO_: {
            data: components["schemas"]["BookDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[CaseDetail] */
        Envelope_CaseDetail_: {
            data: components["schemas"]["CaseDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ConceptDetail] */
        Envelope_ConceptDetail_: {
            data: components["schemas"]["ConceptDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[CorrectionResult] */
        Envelope_CorrectionResult_: {
            data: components["schemas"]["CorrectionResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[DatasetDTO] */
        Envelope_DatasetDTO_: {
            data: components["schemas"]["DatasetDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[EvidenceDTO] */
        Envelope_EvidenceDTO_: {
            data: components["schemas"]["EvidenceDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[GenerationDTO] */
        Envelope_GenerationDTO_: {
            data: components["schemas"]["GenerationDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[JobDetail] */
        Envelope_JobDetail_: {
            data: components["schemas"]["JobDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[LiveStatus] */
        Envelope_LiveStatus_: {
            data: components["schemas"]["LiveStatus"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[LoginResult] */
        Envelope_LoginResult_: {
            data: components["schemas"]["LoginResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[MeDTO] */
        Envelope_MeDTO_: {
            data: components["schemas"]["MeDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[MethodDTO] */
        Envelope_MethodDTO_: {
            data: components["schemas"]["MethodDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[OntologyDiff] */
        Envelope_OntologyDiff_: {
            data: components["schemas"]["OntologyDiff"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[OntologyReleaseDTO] */
        Envelope_OntologyReleaseDTO_: {
            data: components["schemas"]["OntologyReleaseDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[PageRevisionDTO] */
        Envelope_PageRevisionDTO_: {
            data: components["schemas"]["PageRevisionDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ProfileDTO] */
        Envelope_ProfileDTO_: {
            data: components["schemas"]["ProfileDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[PublishOntologyResult] */
        Envelope_PublishOntologyResult_: {
            data: components["schemas"]["PublishOntologyResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[PublishResult] */
        Envelope_PublishResult_: {
            data: components["schemas"]["PublishResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ReadyStatus] */
        Envelope_ReadyStatus_: {
            data: components["schemas"]["ReadyStatus"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[RelationDTO] */
        Envelope_RelationDTO_: {
            data: components["schemas"]["RelationDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ReleaseDTO] */
        Envelope_ReleaseDTO_: {
            data: components["schemas"]["ReleaseDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ReleaseDetail] */
        Envelope_ReleaseDetail_: {
            data: components["schemas"]["ReleaseDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ReviewItemDTO] */
        Envelope_ReviewItemDTO_: {
            data: components["schemas"]["ReviewItemDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ReviewResult] */
        Envelope_ReviewResult_: {
            data: components["schemas"]["ReviewResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[RuleDetail] */
        Envelope_RuleDetail_: {
            data: components["schemas"]["RuleDetail"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[RunDTO] */
        Envelope_RunDTO_: {
            data: components["schemas"]["RunDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[SchoolDTO] */
        Envelope_SchoolDTO_: {
            data: components["schemas"]["SchoolDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ScopeDTO] */
        Envelope_ScopeDTO_: {
            data: components["schemas"]["ScopeDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[SearchResult] */
        Envelope_SearchResult_: {
            data: components["schemas"]["SearchResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[SettingDTO] */
        Envelope_SettingDTO_: {
            data: components["schemas"]["SettingDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[SettingsView] */
        Envelope_SettingsView_: {
            data: components["schemas"]["SettingsView"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[TermDTO] */
        Envelope_TermDTO_: {
            data: components["schemas"]["TermDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[TestResult] */
        Envelope_TestResult_: {
            data: components["schemas"]["TestResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[TopicDTO] */
        Envelope_TopicDTO_: {
            data: components["schemas"]["TopicDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[UploadResult] */
        Envelope_UploadResult_: {
            data: components["schemas"]["UploadResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[UsageDTO] */
        Envelope_UsageDTO_: {
            data: components["schemas"]["UsageDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[UserDTO] */
        Envelope_UserDTO_: {
            data: components["schemas"]["UserDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ValidationResult] */
        Envelope_ValidationResult_: {
            data: components["schemas"]["ValidationResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[VersionDTO] */
        Envelope_VersionDTO_: {
            data: components["schemas"]["VersionDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[WithdrawResult] */
        Envelope_WithdrawResult_: {
            data: components["schemas"]["WithdrawResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[list[Grant]] */
        Envelope_list_Grant__: {
            /** Data */
            data: components["schemas"]["Grant"][];
            meta: components["schemas"]["Meta"];
        };
        /** EvidenceDTO */
        EvidenceDTO: {
            /**
             * Block Id
             * Format: uuid
             */
            block_id: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** End Offset */
            end_offset: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /**
             * Page Id
             * Format: uuid
             */
            page_id: string;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Quote */
            quote: string;
            /**
             * Speaker Layer
             * @enum {string}
             */
            speaker_layer: "original_author" | "commentator" | "translator" | "editor" | "unknown";
            /** Start Offset */
            start_offset: number;
        };
        /** EvidenceGroup */
        EvidenceGroup: {
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Book Title */
            book_title: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** Chunk Ids */
            chunk_ids: string[];
            /** Edition Label */
            edition_label: string;
            /**
             * Evidence Id
             * @description opaque handle a model cites (E1, E2, …)
             */
            evidence_id: string;
            /** Excerpt */
            excerpt: string;
            /** Kinds */
            kinds: string[];
            /** Merged */
            merged: boolean;
            /** Pages */
            pages: number[];
            /** Printed Pages */
            printed_pages: string[];
            /** Rerank Score */
            rerank_score: number | null;
            /** School Key */
            school_key: string | null;
            /** Score */
            score: number;
            /** Section Path */
            section_path: string;
            /** Section Title */
            section_title: string;
            /** Spans */
            spans: components["schemas"]["BundleSpan"][];
            /** Speaker Layer */
            speaker_layer: string;
            /** Tokens */
            tokens: number;
        };
        /** EvidenceInput */
        EvidenceInput: {
            /** End Offset */
            end_offset: number;
            /**
             * Origin
             * @default source_explicit
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Start Offset */
            start_offset: number;
        };
        /** Expansion */
        Expansion: {
            /** Concept */
            concept: string;
            /** Matched */
            matched: string;
            /** School Key */
            school_key: string;
            /** Variants */
            variants: string[];
        };
        /** FieldError */
        FieldError: {
            /** Message */
            message: string;
            /** Path */
            path: string;
        };
        /** Fixture */
        Fixture: {
            /**
             * Expect
             * @enum {string}
             */
            expect: "fired" | "not_matched" | "pending" | "blocked_exception" | "dependency_blocked";
            /** Facts */
            facts: {
                [key: string]: unknown;
            };
            /** Fired Rules */
            fired_rules?: string[] | null;
            /** Name */
            name: string;
        };
        /** FixtureResult */
        FixtureResult: {
            /**
             * Expect
             * @enum {string}
             */
            expect: "fired" | "not_matched" | "pending" | "blocked_exception" | "dependency_blocked";
            /** Name */
            name: string;
            /** Passed */
            passed: boolean;
            /**
             * Status
             * @enum {string}
             */
            status: "fired" | "not_matched" | "pending" | "blocked_exception" | "dependency_blocked";
        };
        /** GenerationDTO */
        GenerationDTO: {
            /** Base Generation Id */
            base_generation_id: string | null;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            coverage: components["schemas"]["PageCoverage"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** In Active Release */
            in_active_release: boolean;
            job: components["schemas"]["JobRef"] | null;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Open Review Items */
            open_review_items: {
                [key: string]: number;
            };
            /**
             * Pipeline Profile Id
             * Format: uuid
             */
            pipeline_profile_id: string;
            /** Release Ids */
            release_ids: string[];
            /** State */
            state: string;
        };
        /** Grant */
        Grant: {
            /**
             * Permission
             * @enum {string}
             */
            permission: "read" | "review" | "manage";
            /** Role Scope */
            role_scope?: ("reader" | "reviewer" | "admin") | null;
            /** User Id */
            user_id?: string | null;
        };
        /** Hit */
        Hit: {
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Book Title */
            book_title: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /** Content Hash */
            content_hash: string;
            /** Edition Label */
            edition_label: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Kind */
            kind: string;
            /** Ordinal */
            ordinal: number;
            /** Pages */
            pages: number[];
            /**
             * Ranks
             * @description rank in each candidate list (lexical, vector)
             */
            ranks: {
                [key: string]: number;
            };
            /** Rerank Score */
            rerank_score?: number | null;
            /** School Key */
            school_key: string | null;
            /**
             * Score
             * @description weighted reciprocal-rank fusion score
             */
            score: number;
            /** Section Path */
            section_path: string;
            /** Section Title */
            section_title: string;
            /** Spans */
            spans: components["schemas"]["HitSpan"][];
            /** Speaker Layer */
            speaker_layer: string;
            /** Text */
            text: string;
        };
        /** HitSpan */
        HitSpan: {
            /**
             * Block Id
             * Format: uuid
             */
            block_id: string;
            /** Chunk End */
            chunk_end: number;
            /** Chunk Start */
            chunk_start: number;
            /** End Offset */
            end_offset: number;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Printed Page Label */
            printed_page_label: string | null;
            /** Start Offset */
            start_offset: number;
        };
        /** ImpactCounts */
        ImpactCounts: {
            /** Assertion */
            assertion: number;
            /** Case Revision */
            case_revision: number;
            /** Chunk Added */
            chunk_added: number;
            /** Chunk Removed */
            chunk_removed: number;
            /** Chunk Reused */
            chunk_reused: number;
            /** Evidence */
            evidence: number;
            /** Page */
            page: number;
            /** Rule */
            rule: number;
            /** Section Added */
            section_added: number;
            /** Section Removed */
            section_removed: number;
        };
        /** ItemDTO */
        ItemDTO: {
            /** Expected */
            expected: {
                [key: string]: unknown;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input */
            input: {
                [key: string]: unknown;
            };
            /** Key */
            key: string;
            /** Kind */
            kind: string;
            /** Reviewer Id */
            reviewer_id: string | null;
            /**
             * Split
             * @enum {string}
             */
            split: "dev" | "test" | "holdout";
        };
        /** ItemExpected */
        ItemExpected: {
            /**
             * No Answer
             * @default false
             */
            no_answer: boolean;
            /** Rationale */
            rationale?: string | null;
            /**
             * Relevant
             * @default []
             */
            relevant: components["schemas"]["RelevantPages"][];
        };
        /** ItemInput */
        ItemInput: {
            /**
             * Book Ids
             * @default []
             */
            book_ids: string[];
            /**
             * Book Version Ids
             * @default []
             */
            book_version_ids: string[];
            /** Query */
            query: string;
            /**
             * School Ids
             * @default []
             */
            school_ids: string[];
            /**
             * Topic Ids
             * @default []
             */
            topic_ids: string[];
        };
        /** JobDTO */
        JobDTO: {
            /**
             * Attempt
             * @description attempt of the unit waiting to retry
             */
            attempt: number | null;
            /** Batch Id */
            batch_id: string | null;
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Book Title */
            book_title: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** Counters */
            counters: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Edition Label */
            edition_label: string;
            error: components["schemas"]["JobError"] | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Job Id */
            parent_job_id: string | null;
            /**
             * Pipeline Profile Id
             * Format: uuid
             */
            pipeline_profile_id: string;
            /** Retry At */
            retry_at: string | null;
            /**
             * Stage
             * @description stage started last
             */
            stage: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "retry_wait" | "waiting_review" | "cancel_requested" | "succeeded" | "partial" | "failed" | "cancelled";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** JobDetail */
        JobDetail: {
            /**
             * Attempt
             * @description attempt of the unit waiting to retry
             */
            attempt: number | null;
            /** Batch Id */
            batch_id: string | null;
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Book Title */
            book_title: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** Counters */
            counters: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Edition Label */
            edition_label: string;
            error: components["schemas"]["JobError"] | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Job Id */
            parent_job_id: string | null;
            /**
             * Pipeline Profile Id
             * Format: uuid
             */
            pipeline_profile_id: string;
            /** Retried By */
            retried_by: string[];
            /** Retry At */
            retry_at: string | null;
            /**
             * Stage
             * @description stage started last
             */
            stage: string | null;
            /** Stages */
            stages: components["schemas"]["StageProgress"][];
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "retry_wait" | "waiting_review" | "cancel_requested" | "succeeded" | "partial" | "failed" | "cancelled";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** JobError */
        JobError: {
            /** Code */
            code: string | null;
            /** Message */
            message: string | null;
            /** Retryable */
            retryable: boolean;
        };
        /** JobEvent */
        JobEvent: {
            /** Code */
            code: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Level
             * @enum {string}
             */
            level: "debug" | "info" | "warning" | "error";
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Seq */
            seq: number;
        };
        /** JobRef */
        JobRef: {
            /** Counters */
            counters: {
                [key: string]: unknown;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** State */
            state: string;
        };
        /** ListEnvelope[AssertionDTO] */
        ListEnvelope_AssertionDTO_: {
            /** Data */
            data: components["schemas"]["AssertionDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[BookDTO] */
        ListEnvelope_BookDTO_: {
            /** Data */
            data: components["schemas"]["BookDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[CaseDTO] */
        ListEnvelope_CaseDTO_: {
            /** Data */
            data: components["schemas"]["CaseDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[ConceptDTO] */
        ListEnvelope_ConceptDTO_: {
            /** Data */
            data: components["schemas"]["ConceptDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[DatasetDTO] */
        ListEnvelope_DatasetDTO_: {
            /** Data */
            data: components["schemas"]["DatasetDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[ItemDTO] */
        ListEnvelope_ItemDTO_: {
            /** Data */
            data: components["schemas"]["ItemDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[JobDTO] */
        ListEnvelope_JobDTO_: {
            /** Data */
            data: components["schemas"]["JobDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[JobEvent] */
        ListEnvelope_JobEvent_: {
            /** Data */
            data: components["schemas"]["JobEvent"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[MethodDTO] */
        ListEnvelope_MethodDTO_: {
            /** Data */
            data: components["schemas"]["MethodDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[OntologyReleaseDTO] */
        ListEnvelope_OntologyReleaseDTO_: {
            /** Data */
            data: components["schemas"]["OntologyReleaseDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[PageSummaryDTO] */
        ListEnvelope_PageSummaryDTO_: {
            /** Data */
            data: components["schemas"]["PageSummaryDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[PipelineProfileDTO] */
        ListEnvelope_PipelineProfileDTO_: {
            /** Data */
            data: components["schemas"]["PipelineProfileDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[ProfileDTO] */
        ListEnvelope_ProfileDTO_: {
            /** Data */
            data: components["schemas"]["ProfileDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[ReviewItemDTO] */
        ListEnvelope_ReviewItemDTO_: {
            /** Data */
            data: components["schemas"]["ReviewItemDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[RuleDTO] */
        ListEnvelope_RuleDTO_: {
            /** Data */
            data: components["schemas"]["RuleDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[SchoolDTO] */
        ListEnvelope_SchoolDTO_: {
            /** Data */
            data: components["schemas"]["SchoolDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[ScopeDTO] */
        ListEnvelope_ScopeDTO_: {
            /** Data */
            data: components["schemas"]["ScopeDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[TermHit] */
        ListEnvelope_TermHit_: {
            /** Data */
            data: components["schemas"]["TermHit"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[TopicDTO] */
        ListEnvelope_TopicDTO_: {
            /** Data */
            data: components["schemas"]["TopicDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[UserDTO] */
        ListEnvelope_UserDTO_: {
            /** Data */
            data: components["schemas"]["UserDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** ListEnvelope[VersionDTO] */
        ListEnvelope_VersionDTO_: {
            /** Data */
            data: components["schemas"]["VersionDTO"][];
            meta: components["schemas"]["Meta"];
            page?: components["schemas"]["Page"];
        };
        /** LiveStatus */
        LiveStatus: {
            /**
             * Status
             * @constant
             */
            status: "ok";
        };
        /** LoginInput */
        LoginInput: {
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** LoginResult */
        LoginResult: {
            /** Csrf Token */
            csrf_token: string;
            user: components["schemas"]["MeDTO"];
        };
        /** MeDTO */
        MeDTO: {
            /** Capabilities */
            capabilities: string[];
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "reviewer" | "reader";
        };
        /** Meta */
        Meta: {
            /** Request Id */
            request_id: string | null;
        };
        /** MethodDTO */
        MethodDTO: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Key */
            key: string;
            /** Revision */
            revision: number;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** MethodInput */
        MethodInput: {
            /** Description */
            description: string;
            /** Key */
            key: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
        };
        /** MethodRevisionInput */
        MethodRevisionInput: {
            /** Base Revision */
            base_revision: number;
            /** Description */
            description: string;
            /** Reason */
            reason: string;
        };
        /** OntologyDiff */
        OntologyDiff: {
            /** Base Release Id */
            base_release_id: string | null;
            /** Base Version */
            base_version: string | null;
            /** Changed */
            changed: boolean;
            concepts: components["schemas"]["Changes"];
            /** Manifest Hash */
            manifest_hash: string;
            terms: components["schemas"]["Changes"];
        };
        /** OntologyReleaseDTO */
        OntologyReleaseDTO: {
            /** Concepts */
            concepts: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Pinned By Active Corpus */
            pinned_by_active_corpus: boolean;
            /**
             * State
             * @enum {string}
             */
            state: "building" | "published" | "retired";
            /** Terms */
            terms: number;
            /** Version */
            version: string;
        };
        /** Page */
        Page: {
            /**
             * Has More
             * @default false
             */
            has_more: boolean;
            /** Next Cursor */
            next_cursor?: string | null;
        };
        /** PageCoverage */
        PageCoverage: {
            /** Accepted */
            accepted: number;
            /** Excluded */
            excluded: number;
            /**
             * Excluded Ranges
             * @description physical pages not accepted, e.g. "3-5"
             */
            excluded_ranges: string[];
            /** Missing */
            missing: number;
            /** Review Required */
            review_required: number;
            /** Total */
            total: number;
        };
        /** PageLayout */
        PageLayout: {
            /** Height */
            height: number | null;
            /** Page Class */
            page_class: string | null;
            /** Rotation */
            rotation: number | null;
            /** Width */
            width: number | null;
        };
        /** PageRevisionDTO */
        PageRevisionDTO: {
            /** Base Revision Id */
            base_revision_id: string | null;
            /** Blocks */
            blocks: components["schemas"]["BlockDTO"][];
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Latest */
            is_latest: boolean;
            /**
             * Latest Revision Id
             * Format: uuid
             */
            latest_revision_id: string;
            layout: components["schemas"]["PageLayout"];
            /**
             * Page Id
             * Format: uuid
             */
            page_id: string;
            /** Page Kind */
            page_kind: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Printed Label Verified */
            printed_label_verified: boolean;
            /** Printed Page Label */
            printed_page_label: string | null;
            /** Quality */
            quality: {
                [key: string]: unknown;
            };
            /** Revision No */
            revision_no: number;
            /**
             * State
             * @enum {string}
             */
            state: "accepted" | "review_required" | "excluded";
            /** Text */
            text: string;
        };
        /** PageSummaryDTO */
        PageSummaryDTO: {
            /**
             * Page Id
             * Format: uuid
             */
            page_id: string;
            /** Page Kind */
            page_kind: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Printed Label Verified */
            printed_label_verified: boolean;
            /** Printed Page Label */
            printed_page_label: string | null;
            /** Quality */
            quality: {
                [key: string]: unknown;
            };
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Revision No */
            revision_no: number;
            /**
             * State
             * @enum {string}
             */
            state: "accepted" | "review_required" | "excluded";
        };
        /** PipelineProfileDTO */
        PipelineProfileDTO: {
            /** Chunker Version */
            chunker_version: string;
            /** Config */
            config: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            embedding: components["schemas"]["EmbeddingRef"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Normalizer Version */
            normalizer_version: string;
            /** Parser Version */
            parser_version: string;
            /** Renderer Version */
            renderer_version: string | null;
        };
        /** ProcessInput */
        ProcessInput: {
            /**
             * Pipeline Profile Id
             * @description defaults to the profile of the latest generation
             */
            pipeline_profile_id?: string | null;
            /**
             * Scope
             * @description page-level work goes through corrections and review items
             * @default full
             * @constant
             */
            scope: "full";
        };
        /** ProfileDTO */
        ProfileDTO: {
            /** Active */
            active: boolean;
            /** Config */
            config: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dimension */
            dimension: number | null;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Fixture */
            is_fixture: boolean;
            /**
             * Kind
             * @enum {string}
             */
            kind: "llm" | "embedding" | "reranker";
            /** Model Name */
            model_name: string;
            /** Model Revision */
            model_revision: string;
            /** Provider */
            provider: string;
            /** Secret Ref */
            secret_ref: string | null;
        };
        /** ProfileInput */
        ProfileInput: {
            /**
             * Config
             * @description no secrets; base_url, timeout, locality, json_mode, prices, daily_budget…
             */
            config?: {
                [key: string]: unknown;
            };
            /** Dimension */
            dimension?: number | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "llm" | "embedding" | "reranker";
            /** Model Name */
            model_name: string;
            /** Model Revision */
            model_revision: string;
            /** Provider */
            provider: string;
            /**
             * Secret Ref
             * @description name of an allowlisted env var
             */
            secret_ref?: string | null;
        };
        /** PublishInput */
        PublishInput: {
            /**
             * Ack Excluded Ranges
             * @default []
             */
            ack_excluded_ranges: string[];
            /**
             * Activate
             * @description false builds a ready release only
             * @default true
             */
            activate: boolean;
            /**
             * Allow Partial
             * @default false
             */
            allow_partial: boolean;
        };
        /** PublishOntologyInput */
        PublishOntologyInput: {
            /**
             * Version
             * @description defaults to onto-YYYYMMDD-N
             */
            version?: string | null;
        };
        /** PublishOntologyResult */
        PublishOntologyResult: {
            /**
             * Corpus Release Id
             * @description the corpus release that now pins it (none while the corpus is empty)
             */
            corpus_release_id: string | null;
            diff: components["schemas"]["OntologyDiff"];
            release: components["schemas"]["OntologyReleaseDTO"];
        };
        /** PublishResult */
        PublishResult: {
            /** Activated */
            activated: boolean;
            coverage: components["schemas"]["PageCoverage"];
            release: components["schemas"]["ReleaseDTO"];
        };
        /** QueryView */
        QueryView: {
            /** Expansions */
            expansions: components["schemas"]["Expansion"][];
            /** Folded */
            folded: string;
            /** Normalized */
            normalized: string;
        };
        /** ReadyStatus */
        ReadyStatus: {
            /** Checks */
            checks: components["schemas"]["CheckDTO"][];
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "degraded" | "fail";
        };
        /** RelationDTO */
        RelationDTO: {
            /**
             * From Id
             * Format: uuid
             */
            from_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Relation */
            relation: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /**
             * To Id
             * Format: uuid
             */
            to_id: string;
        };
        /** RelationInput */
        RelationInput: {
            /**
             * From Id
             * Format: uuid
             */
            from_id: string;
            /**
             * Relation
             * @enum {string}
             */
            relation: "supports" | "disputes" | "qualifies" | "exception_to" | "derives_from";
            /**
             * To Id
             * Format: uuid
             */
            to_id: string;
        };
        /** ReleaseDTO */
        ReleaseDTO: {
            /** Active */
            active: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Embedding Collection Id
             * Format: uuid
             */
            embedding_collection_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Lexical Profile Version */
            lexical_profile_version: string;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Members Count */
            members_count: number;
            /**
             * Ontology Release Id
             * Format: uuid
             */
            ontology_release_id: string;
            /** Parent Id */
            parent_id: string | null;
            /** State */
            state: string;
        };
        /** ReleaseDetail */
        ReleaseDetail: {
            /** Active */
            active: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Embedding Collection Id
             * Format: uuid
             */
            embedding_collection_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Lexical Profile Version */
            lexical_profile_version: string;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Members */
            members: components["schemas"]["ReleaseMember"][];
            /** Members Count */
            members_count: number;
            /**
             * Ontology Release Id
             * Format: uuid
             */
            ontology_release_id: string;
            /** Parent Id */
            parent_id: string | null;
            /** State */
            state: string;
        };
        /** ReleaseMember */
        ReleaseMember: {
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
        };
        /** ReleasesEnvelope */
        ReleasesEnvelope: {
            data: components["schemas"]["ReleasesView"];
            meta: components["schemas"]["Meta"];
            page: components["schemas"]["Page"];
        };
        /** ReleasesView */
        ReleasesView: {
            /** @description null while the corpus is empty */
            active: components["schemas"]["ActivePointer"] | null;
            /** Releases */
            releases: components["schemas"]["ReleaseDTO"][];
        };
        /** RelevantPages */
        RelevantPages: {
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Grade
             * @default 1
             * @enum {integer}
             */
            grade: 1 | 2;
            /** Pages */
            pages: number[];
        };
        /** RetryInput */
        RetryInput: {
            /**
             * Failed Units Only
             * @description succeeded units are always reused; use /process to rebuild
             * @default true
             */
            failed_units_only: boolean;
        };
        /** ReviewInput */
        ReviewInput: {
            /**
             * Base Revision
             * @description the revision reviewed (1 for terms, scopes, relations)
             */
            base_revision: number;
            /**
             * Decision
             * @enum {string}
             */
            decision: "submit" | "return" | "approve" | "reject" | "revoke";
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /**
             * Entity Kind
             * @enum {string}
             */
            entity_kind: "method" | "concept" | "term" | "school_scope" | "assertion" | "assertion_relation" | "rule" | "case_revision";
            /** Reason */
            reason: string;
        };
        /** ReviewItemDTO */
        ReviewItemDTO: {
            /** Book Title */
            book_title: string | null;
            /** Book Version Id */
            book_version_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Entity Id */
            entity_id: string | null;
            /** Entity Kind */
            entity_kind: string | null;
            /** Generation Id */
            generation_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Page Id */
            page_id: string | null;
            /** Page Revision Id */
            page_revision_id: string | null;
            /** Physical Page Number */
            physical_page_number: number | null;
            /** Reason Code */
            reason_code: string;
            /** Resolution */
            resolution: {
                [key: string]: unknown;
            };
            /**
             * Severity
             * @enum {string}
             */
            severity: "info" | "low" | "medium" | "high" | "critical";
            /**
             * State
             * @enum {string}
             */
            state: "open" | "in_progress" | "resolved" | "dismissed";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ReviewRecord */
        ReviewRecord: {
            /** Base Revision */
            base_revision: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "reject" | "revoke";
            /** Reason */
            reason: string;
            /**
             * Reviewer Id
             * Format: uuid
             */
            reviewer_id: string;
        };
        /** ReviewResult */
        ReviewResult: {
            /**
             * Analyses Stale
             * @description revoke: answers marked stale
             */
            analyses_stale?: number | null;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Entity Kind */
            entity_kind: string;
            /** Job Id */
            job_id?: string | null;
            /**
             * Rebuild
             * @description school scopes: queued or why not
             */
            rebuild?: string | null;
            /** Review Id */
            review_id: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
            /** Terms Approved */
            terms_approved?: number | null;
        };
        /** RuleDTO */
        RuleDTO: {
            /** Assertion Id */
            assertion_id: string | null;
            /**
             * Author Id
             * Format: uuid
             */
            author_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dsl */
            dsl: {
                [key: string]: unknown;
            };
            /** Dsl Hash */
            dsl_hash: string;
            /** Fact Schema Version */
            fact_schema_version: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Method Id
             * Format: uuid
             */
            method_id: string;
            /** Method Key */
            method_key: string;
            /** Revision */
            revision: number;
            /** Rule Key */
            rule_key: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** RuleDetail */
        RuleDetail: {
            /** Assertion Id */
            assertion_id: string | null;
            /**
             * Author Id
             * Format: uuid
             */
            author_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dsl */
            dsl: {
                [key: string]: unknown;
            };
            /** Dsl Hash */
            dsl_hash: string;
            /** Fact Schema Version */
            fact_schema_version: string;
            /** Fixtures */
            fixtures: components["schemas"]["Fixture"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Method Id
             * Format: uuid
             */
            method_id: string;
            /** Method Key */
            method_key: string;
            /** Requires */
            requires: string[];
            /** Reviews */
            reviews: components["schemas"]["RuleReview"][];
            /** Revision */
            revision: number;
            /** Rule Key */
            rule_key: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /** Sources */
            sources: components["schemas"]["RuleSource"][];
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** RuleInput */
        RuleInput: {
            /** Assertion Id */
            assertion_id?: string | null;
            /**
             * Dsl
             * @description a bazi-rule/1 document (docs/08)
             */
            dsl: {
                [key: string]: unknown;
            };
        };
        /** RuleReview */
        RuleReview: {
            /** Base Revision */
            base_revision: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "reject" | "revoke";
            /** Reason */
            reason: string;
            /**
             * Reviewer Id
             * Format: uuid
             */
            reviewer_id: string;
        };
        /** RuleRevisionInput */
        RuleRevisionInput: {
            /** Base Revision */
            base_revision: number;
            /** Dsl */
            dsl: {
                [key: string]: unknown;
            };
            /** Reason */
            reason: string;
        };
        /** RuleSource */
        RuleSource: {
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Evidence Id
             * Format: uuid
             */
            evidence_id: string;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Quote */
            quote: string;
        };
        /** RunDTO */
        RunDTO: {
            /** Config */
            config: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Dataset Id
             * Format: uuid
             */
            dataset_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Metrics
             * @description means of recall@k, hit@k, ndcg@10, mrr@10; latency
             */
            metrics: {
                [key: string]: unknown;
            };
            /** Results */
            results: components["schemas"]["RunResult"][];
            /** Status */
            status: string;
        };
        /** RunInput */
        RunInput: {
            /**
             * Dataset Id
             * Format: uuid
             */
            dataset_id: string;
            /**
             * Rerank
             * @default true
             */
            rerank: boolean;
            /** Split */
            split?: ("dev" | "test" | "holdout") | null;
            /**
             * Top K
             * @default 20
             */
            top_k: number;
        };
        /** RunResult */
        RunResult: {
            /** Actual */
            actual: {
                [key: string]: unknown;
            };
            /** Duration Ms */
            duration_ms: number;
            /** Key */
            key: string;
            /** Scores */
            scores: {
                [key: string]: unknown;
            };
            /**
             * Status
             * @enum {string}
             */
            status: "passed" | "failed" | "error" | "skipped";
        };
        /**
         * RuntimeConfigDTO
         * @description Redacted runtime facts: which providers are configured, never their secrets.
         */
        RuntimeConfigDTO: {
            /** App Env */
            app_env: string;
            /** Embedding Configured */
            embedding_configured: boolean;
            /** Llm Configured */
            llm_configured: boolean;
            /** Llm Provider */
            llm_provider: string;
            /** Storage Backend */
            storage_backend: string;
        };
        /** SchoolDTO */
        SchoolDTO: {
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Parent Id */
            parent_id: string | null;
        };
        /** SchoolInput */
        SchoolInput: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Parent Id */
            parent_id?: string | null;
        };
        /** ScopeDTO */
        ScopeDTO: {
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** First Page */
            first_page: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Page */
            last_page: number | null;
            /** Reason */
            reason: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
            /** School Key */
            school_key: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** ScopeInput */
        ScopeInput: {
            /** First Page */
            first_page?: number | null;
            /** Last Page */
            last_page?: number | null;
            /** Reason */
            reason: string;
            /**
             * School Id
             * Format: uuid
             */
            school_id: string;
        };
        /** SearchInput */
        SearchInput: {
            /**
             * Book Ids
             * @default []
             */
            book_ids: string[];
            /**
             * Book Version Ids
             * @default []
             */
            book_version_ids: string[];
            /**
             * Mode
             * @default research
             * @enum {string}
             */
            mode: "research" | "chart_analysis" | "comparison";
            /**
             * Pack
             * @description also return the packed evidence bundle
             * @default false
             */
            pack: boolean;
            /** Page From */
            page_from?: number | null;
            /** Page To */
            page_to?: number | null;
            /** Query */
            query: string;
            /**
             * Rerank
             * @description order the top 40 with the active reranker
             * @default true
             */
            rerank: boolean;
            /**
             * School Ids
             * @default []
             */
            school_ids: string[];
            /**
             * Top K
             * @default 8
             */
            top_k: number;
            /**
             * Topic Ids
             * @default []
             */
            topic_ids: string[];
        };
        /** SearchResult */
        SearchResult: {
            bundle?: components["schemas"]["Bundle"] | null;
            /** Counts */
            counts?: {
                [key: string]: number;
            };
            /** Degraded */
            degraded: string[];
            /** Hits */
            hits: components["schemas"]["Hit"][];
            query: components["schemas"]["QueryView"];
            /** Release Id */
            release_id: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "no_match" | "empty_corpus" | "empty_filters";
            /** Took Ms */
            took_ms?: number | null;
            /** Visibility Epoch */
            visibility_epoch: number | null;
        };
        /** SettingDTO */
        SettingDTO: {
            /** Key */
            key: string;
            /** Revision */
            revision: number;
            /**
             * Scope
             * @enum {string}
             */
            scope: "system" | "user";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Value */
            value: unknown;
        };
        /** SettingPatch */
        SettingPatch: {
            /** Key */
            key: string;
            /**
             * Scope
             * @enum {string}
             */
            scope: "system" | "user";
            /** Value */
            value: unknown;
        };
        /** SettingsView */
        SettingsView: {
            runtime: components["schemas"]["RuntimeConfigDTO"];
            /** Settings */
            settings: components["schemas"]["SettingDTO"][];
        };
        /** SourceChanged */
        SourceChanged: {
            /** Assertion */
            assertion: string[];
            /** Case Revision */
            case_revision: string[];
            /** Evidence */
            evidence: string[];
            /** Rule */
            rule: string[];
        };
        /** SourceDTO */
        SourceDTO: {
            /**
             * Block Id
             * Format: uuid
             */
            block_id: string;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** End Offset */
            end_offset: number;
            /**
             * Evidence Id
             * Format: uuid
             */
            evidence_id: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "source_explicit" | "editor_interpretation" | "ai_inferred";
            /**
             * Page Id
             * Format: uuid
             */
            page_id: string;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Quote */
            quote: string;
            /**
             * Relation
             * @enum {string}
             */
            relation: "states" | "supports" | "contrasts";
            /**
             * Speaker Layer
             * @enum {string}
             */
            speaker_layer: "original_author" | "commentator" | "translator" | "editor" | "unknown";
            /** Start Offset */
            start_offset: number;
        };
        /** StageProgress */
        StageProgress: {
            /** Computed */
            computed: number;
            /** Done */
            done: boolean;
            /** Reused */
            reused: number;
            /** Stage */
            stage: string;
            /** Units */
            units: number;
        };
        /** TermDTO */
        TermDTO: {
            /**
             * Alias Kind
             * @enum {string}
             */
            alias_kind: "canonical" | "same_concept" | "translation_variant" | "related" | "contrasts_with";
            /**
             * Concept Id
             * Format: uuid
             */
            concept_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Evidence Id */
            evidence_id: string | null;
            /** Form */
            form: string;
            /** Form Folded */
            form_folded: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Language */
            language: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** TermHit */
        TermHit: {
            /**
             * Alias Kind
             * @enum {string}
             */
            alias_kind: "canonical" | "same_concept" | "translation_variant" | "related" | "contrasts_with";
            concept: components["schemas"]["ConceptRef"];
            /**
             * Concept Id
             * Format: uuid
             */
            concept_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Evidence Id */
            evidence_id: string | null;
            /** Form */
            form: string;
            /** Form Folded */
            form_folded: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Language */
            language: string;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** TermInput */
        TermInput: {
            /**
             * Alias Kind
             * @enum {string}
             */
            alias_kind: "same_concept" | "translation_variant" | "related" | "contrasts_with";
            /**
             * Concept Id
             * Format: uuid
             */
            concept_id: string;
            /** Evidence Id */
            evidence_id?: string | null;
            /** Form */
            form: string;
            /**
             * Language
             * @default vi
             */
            language: string;
        };
        /** TestInput */
        TestInput: {
            /**
             * Check Json
             * @default false
             */
            check_json: boolean;
            /**
             * Max Tokens
             * @default 16
             */
            max_tokens: number;
        };
        /** TestResult */
        TestResult: {
            /** Dimension */
            dimension?: number | null;
            /** Input Tokens */
            input_tokens?: number | null;
            /** Is Fixture */
            is_fixture: boolean;
            /** Json Ok */
            json_ok?: boolean | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "llm" | "embedding" | "reranker";
            /** Latency Ms */
            latency_ms: number;
            /** Model */
            model: string;
            /** Output Tokens */
            output_tokens?: number | null;
            /** Reply */
            reply?: string | null;
        };
        /** TopicDTO */
        TopicDTO: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Parent Id */
            parent_id: string | null;
        };
        /** TopicInput */
        TopicInput: {
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Parent Id */
            parent_id?: string | null;
        };
        /** UploadResult */
        UploadResult: {
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            /** Display Name */
            display_name: string;
            /** Duplicate Of */
            duplicate_of?: string | null;
            /** Job Id */
            job_id?: string | null;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "accepted" | "duplicate";
            /** Sha256 */
            sha256: string;
            /** Size Bytes */
            size_bytes: number;
            /** Version Id */
            version_id?: string | null;
        };
        /** UsageDTO */
        UsageDTO: {
            /**
             * All
             * @description admins: totals of everyone
             */
            all?: components["schemas"]["UsageRow"][] | null;
            /** Budgets */
            budgets: components["schemas"]["BudgetRow"][];
            /**
             * From
             * Format: date-time
             */
            from: string;
            /** Own */
            own: components["schemas"]["UsageRow"][];
            /**
             * To
             * Format: date-time
             */
            to: string;
        };
        /** UsageRow */
        UsageRow: {
            /** Cost */
            cost: number;
            /** Currency */
            currency: string;
            /** Input Tokens */
            input_tokens: number;
            /** Output Tokens */
            output_tokens: number;
            /**
             * Profile Id
             * Format: uuid
             */
            profile_id: string;
            /** Requests */
            requests: number;
        };
        /** UserCreate */
        UserCreate: {
            /** Email */
            email: string;
            /** Password */
            password: string;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "reviewer" | "reader";
        };
        /** UserDTO */
        UserDTO: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            /** Enabled */
            enabled: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Locale */
            locale: string;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "reviewer" | "reader";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** UserPatch */
        UserPatch: {
            /** Enabled */
            enabled?: boolean | null;
            /** Role */
            role?: ("reader" | "reviewer" | "admin") | null;
        };
        /** ValidateInput */
        ValidateInput: {
            /**
             * Fixtures
             * @description replaces the stored fixtures of a draft
             * @default []
             */
            fixtures: components["schemas"]["Fixture"][];
        };
        /** ValidationResult */
        ValidationResult: {
            /** Approvable Fixtures */
            approvable_fixtures: boolean;
            /** Errors */
            errors: components["schemas"]["DslProblem"][];
            /**
             * Problem
             * @description what still blocks approval, if anything
             */
            problem: string | null;
            /** Results */
            results: components["schemas"]["FixtureResult"][];
            /**
             * Rule Id
             * Format: uuid
             */
            rule_id: string;
            /** Valid */
            valid: boolean;
        };
        /** VersionDTO */
        VersionDTO: {
            /**
             * Book Id
             * Format: uuid
             */
            book_id: string;
            coverage: components["schemas"]["Coverage"];
            /** Current Generation Id */
            current_generation_id: string | null;
            /** Edition Label */
            edition_label: string;
            /** External Processing Allowed */
            external_processing_allowed: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Mime */
            mime: string;
            /** Rights Status */
            rights_status: string;
            /** Sha256 */
            sha256: string;
            /** Size Bytes */
            size_bytes: number;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "withdrawn";
            /** Version No */
            version_no: number;
        };
        /** ViewerSpan */
        ViewerSpan: {
            /** Bbox */
            bbox: number[] | null;
            /** End Offset */
            end_offset: number;
            /**
             * Page Revision Id
             * Format: uuid
             */
            page_revision_id: string;
            /** Physical Page Number */
            physical_page_number: number;
            /** Printed Page Label */
            printed_page_label: string | null;
            /** Start Offset */
            start_offset: number;
        };
        /** WithdrawInput */
        WithdrawInput: {
            /** Reason */
            reason: string;
        };
        /** WithdrawResult */
        WithdrawResult: {
            /**
             * Active Release Id
             * @description the release now active, if any
             */
            active_release_id: string | null;
            /**
             * Book Version Id
             * Format: uuid
             */
            book_version_id: string;
            /** Status */
            status: string;
            /** Visibility Epoch */
            visibility_epoch: number | null;
        };
        /** RevisionRef */
        backend__app__api__knowledge__RevisionRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision */
            revision: number;
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "in_review" | "approved" | "rejected" | "revoked";
        };
        /** ImpactDTO */
        backend__app__api__ontology__ImpactDTO: {
            /** Counts */
            counts: {
                [key: string]: number;
            };
            /** @description owner-private answers counted, never listed */
            dependents: components["schemas"]["Dependents"];
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Entity Kind */
            entity_kind: string;
            /**
             * Ids
             * @description first 100 per kind
             */
            ids: {
                [key: string]: string[];
            };
        };
        /** ImpactDTO */
        backend__app__api__pages__ImpactDTO: {
            /** Base Generation Id */
            base_generation_id: string | null;
            counts: components["schemas"]["ImpactCounts"];
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Ids */
            ids: string[];
            job: components["schemas"]["JobRef"] | null;
            /** Kind */
            kind: ("page" | "chunk_added" | "chunk_removed" | "evidence" | "rule" | "assertion" | "case_revision") | null;
            /**
             * Next Cursor
             * @description cursor for the next page of ids of kind
             */
            next_cursor: string | null;
            /** State */
            state: string;
        };
        /** RevisionRef */
        backend__app__api__pages__RevisionRef: {
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Page Id
             * Format: uuid
             */
            page_id: string;
            /** Revision No */
            revision_no: number;
        };
        /** ResolveInput */
        backend__app__api__reviews__ResolveInput: {
            /**
             * Action
             * @enum {string}
             */
            action: "accept" | "exclude" | "retry" | "dismiss";
            /**
             * Base Revision Id
             * @description the page revision reviewed (required except for dismiss)
             */
            base_revision_id?: string | null;
            /** Reason */
            reason: string;
        };
        /** ResolveResult */
        backend__app__api__reviews__ResolveResult: {
            /** Coalesced */
            coalesced: boolean;
            /** Generation Id */
            generation_id: string | null;
            item: components["schemas"]["ReviewItemDTO"];
            /** Job Id */
            job_id: string | null;
        };
        /** Envelope[ImpactDTO] */
        backend__app__api__schemas__Envelope_ImpactDTO___1: {
            data: components["schemas"]["backend__app__api__pages__ImpactDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ImpactDTO] */
        backend__app__api__schemas__Envelope_ImpactDTO___2: {
            data: components["schemas"]["backend__app__api__ontology__ImpactDTO"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ResolveResult] */
        backend__app__api__schemas__Envelope_ResolveResult___1: {
            data: components["schemas"]["backend__app__api__reviews__ResolveResult"];
            meta: components["schemas"]["Meta"];
        };
        /** Envelope[ResolveResult] */
        backend__app__api__schemas__Envelope_ResolveResult___2: {
            data: components["schemas"]["backend__app__api__search__ResolveResult"];
            meta: components["schemas"]["Meta"];
        };
        /**
         * Problem
         * @description application/problem+json (RFC 9457) with a stable ``code``.
         */
        backend__app__api__schemas__Problem: {
            /** Code */
            code: string;
            /** Detail */
            detail: string | null;
            /**
             * Field Errors
             * @default []
             */
            field_errors: components["schemas"]["FieldError"][];
            /** Request Id */
            request_id: string | null;
            /** Status */
            status: number;
            /** Title */
            title: string;
            /** Type */
            type: string;
        };
        /** Problem */
        backend__app__api__search__Problem: {
            /**
             * Code
             * @enum {string}
             */
            code: "UNKNOWN_EVIDENCE" | "SOURCE_WITHDRAWN" | "SPAN_INVALID" | "SOURCE_CHANGED" | "QUOTE_MISMATCH";
            /** Evidence Id */
            evidence_id: string;
        };
        /** ResolveInput */
        backend__app__api__search__ResolveInput: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Claims */
            claims: components["schemas"]["ClaimInput"][];
        };
        /** ResolveResult */
        backend__app__api__search__ResolveResult: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Claims */
            claims: components["schemas"]["ClaimResult"][];
            /** Epoch Changed */
            epoch_changed: boolean;
            /**
             * Release Id
             * Format: uuid
             */
            release_id: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    create_relation_api_v1_assertion_relations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RelationInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RelationDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_assertions_api_v1_assertions_get: {
        parameters: {
            query?: {
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
                school_id?: string | null;
                book_version_id?: string | null;
                q?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_AssertionDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_assertion_api_v1_assertions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssertionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_AssertionDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_assertion_api_v1_assertions__assertion_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assertion_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_AssertionDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    revise_assertion_api_v1_assertions__assertion_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assertion_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssertionRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_AssertionDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_LoginResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MeDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_version_api_v1_book_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_VersionDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_pages_api_v1_book_versions__version_id__pages_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_PageSummaryDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    process_version_api_v1_book_versions__version_id__process_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProcessInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_JobDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_scopes_api_v1_book_versions__version_id__school_scopes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_ScopeDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_scope_api_v1_book_versions__version_id__school_scopes_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScopeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ScopeDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    withdraw_api_v1_book_versions__version_id__withdraw_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WithdrawInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_WithdrawResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_books_api_v1_books_get: {
        parameters: {
            query?: {
                q?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_BookDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_book_api_v1_books_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BookDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_book_api_v1_books__book_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BookDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    patch_book_api_v1_books__book_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BookDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_access_api_v1_books__book_id__access_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_Grant__"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    put_access_api_v1_books__book_id__access_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccessInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_Grant__"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    versions_api_v1_books__book_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_VersionDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_cases_api_v1_cases_get: {
        parameters: {
            query?: {
                school_id?: string | null;
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
                origin?: ("book_case" | "user_case" | "synthetic_test") | null;
                book_version_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_CaseDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_case_api_v1_cases_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_CaseDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_case_api_v1_cases__case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_CaseDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    delete_case_api_v1_cases__case_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    revise_case_api_v1_cases__case_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_CaseDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    resolve_citations_api_v1_citations_resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["backend__app__api__search__ResolveInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Envelope_ResolveResult___2"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_concepts_api_v1_concepts_get: {
        parameters: {
            query?: {
                school_id?: string | null;
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
                q?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_ConceptDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_concept_api_v1_concepts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConceptInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ConceptDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_concept_api_v1_concepts__concept_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                concept_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ConceptDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    revise_concept_api_v1_concepts__concept_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                concept_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConceptRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ConceptDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_releases_api_v1_corpus_releases_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReleasesEnvelope"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_release_api_v1_corpus_releases__release_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReleaseDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    activate_api_v1_corpus_releases__release_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActivateInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReleaseDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_datasets_api_v1_evaluation_datasets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_DatasetDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_dataset_api_v1_evaluation_datasets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DatasetInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_DatasetDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    approve_dataset_api_v1_evaluation_datasets__dataset_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_DatasetDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_items_api_v1_evaluation_datasets__dataset_id__items_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_ItemDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_run_api_v1_evaluation_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RunDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_run_api_v1_evaluation_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RunDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_evidence_api_v1_evidence_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvidenceInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EvidenceDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_evidence_api_v1_evidence__evidence_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EvidenceDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_generation_api_v1_generations__generation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_GenerationDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    generation_impact_api_v1_generations__generation_id__impact_get: {
        parameters: {
            query?: {
                kind?: ("page" | "chunk_added" | "chunk_removed" | "evidence" | "rule" | "assertion" | "case_revision") | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Envelope_ImpactDTO___1"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    publish_api_v1_generations__generation_id__publish_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublishInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PublishResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    live_api_v1_health_live_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_LiveStatus_"];
                };
            };
        };
    };
    ready_api_v1_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReadyStatus_"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReadyStatus_"];
                };
            };
        };
    };
    new_batch_api_v1_ingestion_batches_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BatchInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BatchDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_batch_api_v1_ingestion_batches__batch_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BatchDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_jobs_api_v1_jobs_get: {
        parameters: {
            query?: {
                state?: ("queued" | "running" | "retry_wait" | "waiting_review" | "cancel_requested" | "succeeded" | "partial" | "failed" | "cancelled") | null;
                batch_id?: string | null;
                book_version_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_JobDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_job_api_v1_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_JobDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    cancel_job_api_v1_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description already terminal */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_JobDetail_"];
                };
            };
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_JobDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    job_events_api_v1_jobs__job_id__events_get: {
        parameters: {
            query?: {
                after_seq?: number;
                limit?: number;
            };
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_JobEvent_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    retry_job_api_v1_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_JobDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    knowledge_impact_api_v1_knowledge_impact_get: {
        parameters: {
            query: {
                entity_kind: string;
                entity_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Envelope_ImpactDTO___2"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_methods_api_v1_methods_get: {
        parameters: {
            query?: {
                school_id?: string | null;
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_MethodDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_method_api_v1_methods_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MethodInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MethodDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_method_api_v1_methods__method_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                method_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MethodDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    revise_method_api_v1_methods__method_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                method_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MethodRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MethodDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_profiles_api_v1_model_profiles_get: {
        parameters: {
            query?: {
                kind?: ("llm" | "embedding" | "reranker") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_ProfileDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_profile_api_v1_model_profiles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ProfileDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    activate_api_v1_model_profiles__profile_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ProfileDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    test_profile_api_v1_model_profiles__profile_id__test_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TestInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TestResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_releases_api_v1_ontology_releases_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_OntologyReleaseDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    publish_api_v1_ontology_releases_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublishOntologyInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PublishOntologyResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    preview_api_v1_ontology_releases_preview_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_OntologyDiff_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_release_api_v1_ontology_releases__release_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_OntologyReleaseDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_revision_api_v1_page_revisions__revision_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PageRevisionDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    render_page_api_v1_page_revisions__revision_id__render_get: {
        parameters: {
            query?: {
                /** @description 1.0 = 72 dpi; capped at 8 million pixels */
                scale?: number;
            };
            header?: never;
            path: {
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description PNG of the page */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "image/png": unknown;
                };
            };
            /** @description unchanged (If-None-Match) */
            304: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    correct_page_api_v1_pages__page_id__corrections_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrectionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_CorrectionResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    pipeline_profiles_api_v1_pipeline_profiles_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_PipelineProfileDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_items_api_v1_review_items_get: {
        parameters: {
            query?: {
                state?: ("open" | "in_progress" | "resolved" | "dismissed") | null;
                reason?: string | null;
                book_version_id?: string | null;
                generation_id?: string | null;
                /** @description page: source pages (OCR, quality); knowledge: candidates and changed sources of entities */
                scope?: ("page" | "knowledge") | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_ReviewItemDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_item_api_v1_review_items__item_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReviewItemDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    resolve_api_v1_review_items__item_id__resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["backend__app__api__reviews__ResolveInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Envelope_ResolveResult___1"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    review_api_v1_reviews_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ReviewResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_rules_api_v1_rules_get: {
        parameters: {
            query?: {
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
                school_id?: string | null;
                method_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_RuleDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_rule_api_v1_rules_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RuleInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RuleDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_rule_api_v1_rules__rule_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RuleDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    revise_rule_api_v1_rules__rule_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RuleRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RuleDetail_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    validate_rule_api_v1_rules__rule_id__validate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ValidateInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ValidationResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_schools_api_v1_schools_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_SchoolDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_school_api_v1_schools_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SchoolInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_SchoolDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_school_api_v1_schools__school_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                school_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_SchoolDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    run_search_api_v1_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_SearchResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_settings_api_v1_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_SettingsView_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    patch_setting_api_v1_settings_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_SettingDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    search_terms_api_v1_terms_get: {
        parameters: {
            query?: {
                q?: string | null;
                school_id?: string | null;
                concept_id?: string | null;
                state?: ("draft" | "in_review" | "approved" | "rejected" | "revoked") | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_TermHit_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_term_api_v1_terms_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TermInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TermDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_term_api_v1_terms__term_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                term_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TermDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    list_topics_api_v1_topics_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_TopicDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_topic_api_v1_topics_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TopicInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TopicDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    upload_api_v1_uploads_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_api_v1_uploads_post"];
            };
        };
        responses: {
            /** @description duplicate_of */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UploadResult_"];
                };
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UploadResult_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    usage_api_v1_usage_get: {
        parameters: {
            query?: {
                from?: string | null;
                to?: string | null;
                profile_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UsageDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    users_api_v1_users_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListEnvelope_UserDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    create_api_v1_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    get_user_api_v1_users__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
    patch_api_v1_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserDTO_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Failed */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Precondition Required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["backend__app__api__schemas__Problem"];
                    "application/problem+json": unknown;
                };
            };
        };
    };
}
