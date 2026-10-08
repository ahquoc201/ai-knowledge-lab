from uuid import uuid4

from fastapi.testclient import TestClient


def register_and_login(
    client: TestClient,
    *,
    email: str,
    password: str,
) -> str:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Document Test User",
        },
    )

    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def test_document_creation_and_user_isolation(client: TestClient):
    password = "TestPassword123!"

    user_a_email = f"user-a-{uuid4()}@example.com"
    user_b_email = f"user-b-{uuid4()}@example.com"

    user_a_token = register_and_login(
        client,
        email=user_a_email,
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=user_b_email,
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "User A document",
            "content": "Private knowledge belonging to User A.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    created_document = create_response.json()

    assert created_document["title"] == "User A document"
    assert created_document["status"] == "pending"

    user_a_documents = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
    )

    assert user_a_documents.status_code == 200

    user_a_data = user_a_documents.json()

    assert user_a_data["total"] >= 1
    assert user_a_data["limit"] == 20
    assert user_a_data["offset"] == 0

    assert any(
        document["id"] == created_document["id"]
        for document in user_a_data["items"]
    )

    user_b_documents = client.get(
        "/api/v1/documents",
        headers=user_b_headers,
    )

    assert user_b_documents.status_code == 200

    user_b_data = user_b_documents.json()

    assert all(
        document["id"] != created_document["id"]
        for document in user_b_data["items"]
    )

    user_a_get_response = client.get(
        f"/api/v1/documents/{created_document['id']}",
        headers=user_a_headers,
    )

    assert user_a_get_response.status_code == 200
    assert user_a_get_response.json()["id"] == created_document["id"]

    user_b_get_response = client.get(
        f"/api/v1/documents/{created_document['id']}",
        headers=user_b_headers,
    )

    assert user_b_get_response.status_code == 404
    assert user_b_get_response.json() == {
        "detail": "Document not found",
    }


def test_delete_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-delete-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-delete-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "Document to delete",
            "content": "This document will be deleted.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=user_b_headers,
    )

    assert user_b_delete_response.status_code == 404
    assert user_b_delete_response.json() == {
        "detail": "Document not found",
    }

    owner_get_response = client.get(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert owner_get_response.status_code == 200

    delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert delete_response.status_code == 204
    assert delete_response.content == b""

    deleted_get_response = client.get(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert deleted_get_response.status_code == 404
    assert deleted_get_response.json() == {
        "detail": "Document not found",
    }


def test_reprocess_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-reprocess-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-reprocess-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "Document to reprocess",
            "content": "PostgreSQL is a relational database system.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_b_headers,
    )

    assert user_b_response.status_code == 404
    assert user_b_response.json() == {
        "detail": "Document not found",
    }

    reprocess_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_a_headers,
    )

    assert reprocess_response.status_code == 200

    reprocessed_document = reprocess_response.json()

    assert reprocessed_document["id"] == document_id
    assert reprocessed_document["status"] == "ready"

    chunks_response = client.get(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_a_headers,
    )

    assert chunks_response.status_code == 200
    assert len(chunks_response.json()) > 0


def test_reprocess_rejects_unsupported_documents(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-reprocess-validation-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    file_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Existing file",
            "content": "Previously extracted content",
            "source_type": "file",
        },
    )

    assert file_response.status_code == 201

    file_document_id = file_response.json()["id"]

    file_reprocess_response = client.post(
        f"/api/v1/documents/{file_document_id}/reprocess",
        headers=headers,
    )

    assert file_reprocess_response.status_code == 409
    assert file_reprocess_response.json() == {
        "detail": "Only text documents can currently be reprocessed",
    }

    empty_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Empty document",
            "content": "   ",
            "source_type": "text",
        },
    )

    assert empty_response.status_code == 201

    empty_document_id = empty_response.json()["id"]

    empty_reprocess_response = client.post(
        f"/api/v1/documents/{empty_document_id}/reprocess",
        headers=headers,
    )

    assert empty_reprocess_response.status_code == 422
    assert empty_reprocess_response.json() == {
        "detail": "Document content is empty",
    }


def test_update_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-update-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-update-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "Original title",
            "content": "Original content",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_b_headers,
        json={
            "title": "Unauthorized update",
        },
    )

    assert user_b_response.status_code == 404
    assert user_b_response.json() == {
        "detail": "Document not found",
    }

    title_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
        json={
            "title": "Updated title",
        },
    )

    assert title_response.status_code == 200
    assert title_response.json()["title"] == "Updated title"
    assert title_response.json()["content"] == "Original content"
    assert title_response.json()["status"] == "pending"

    reprocess_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_a_headers,
    )

    assert reprocess_response.status_code == 200
    assert reprocess_response.json()["status"] == "ready"

    content_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
        json={
            "content": "Updated content for reprocessing.",
        },
    )

    assert content_response.status_code == 200
    assert content_response.json()["content"] == (
        "Updated content for reprocessing."
    )
    assert content_response.json()["status"] == "pending"


def test_update_document_validation(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-update-validation-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    file_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Uploaded file",
            "content": "Extracted content",
            "source_type": "file",
        },
    )

    assert file_response.status_code == 201

    file_document_id = file_response.json()["id"]

    file_update_response = client.patch(
        f"/api/v1/documents/{file_document_id}",
        headers=headers,
        json={
            "content": "Changed content",
        },
    )

    assert file_update_response.status_code == 409
    assert file_update_response.json() == {
        "detail": "File document content cannot be updated",
    }

    text_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Text document",
            "content": "Content",
            "source_type": "text",
        },
    )

    assert text_response.status_code == 201

    text_document_id = text_response.json()["id"]

    null_title_response = client.patch(
        f"/api/v1/documents/{text_document_id}",
        headers=headers,
        json={
            "title": None,
        },
    )

    assert null_title_response.status_code == 422
    assert null_title_response.json() == {
        "detail": "Document title cannot be null",
    }


def test_list_documents_search_filter_pagination_and_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-search-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-search-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    def create_document(
        headers,
        *,
        title,
        content,
        source_type="text",
    ):
        response = client.post(
            "/api/v1/documents",
            headers=headers,
            json={
                "title": title,
                "content": content,
                "source_type": source_type,
            },
        )

        assert response.status_code == 201
        return response.json()

    postgres_ready = create_document(
        user_a_headers,
        title="PostgreSQL Ready Guide",
        content="PostgreSQL indexing knowledge.",
    )

    create_document(
        user_a_headers,
        title="PostgreSQL Pending Notes",
        content="Pending PostgreSQL knowledge.",
    )

    redis_ready = create_document(
        user_a_headers,
        title="Redis Ready Guide",
        content="Redis caching knowledge.",
    )

    file_document = create_document(
        user_a_headers,
        title="PostgreSQL File",
        content="Extracted file content.",
        source_type="file",
    )

    user_b_document = create_document(
        user_b_headers,
        title="PostgreSQL Ready Secret",
        content="Another user's private knowledge.",
    )

    for document in (
        postgres_ready,
        redis_ready,
        user_b_document,
    ):
        headers = (
            user_a_headers
            if document["id"] != user_b_document["id"]
            else user_b_headers
        )

        response = client.post(
            f"/api/v1/documents/{document['id']}/reprocess",
            headers=headers,
        )

        assert response.status_code == 200

    filtered_response = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
        params={
            "search": "postgres",
            "status": "ready",
            "source_type": "text",
        },
    )

    assert filtered_response.status_code == 200

    filtered_data = filtered_response.json()
    filtered_documents = filtered_data["items"]

    assert filtered_data["total"] == 1
    assert filtered_data["limit"] == 20
    assert filtered_data["offset"] == 0

    assert [
        document["id"]
        for document in filtered_documents
    ] == [postgres_ready["id"]]

    file_response = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
        params={
            "source_type": "file",
        },
    )

    assert file_response.status_code == 200

    file_data = file_response.json()

    assert file_data["total"] == 1
    assert file_data["limit"] == 20
    assert file_data["offset"] == 0

    assert [
        document["id"]
        for document in file_data["items"]
    ] == [file_document["id"]]

    all_text_response = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
        params={
            "source_type": "text",
            "limit": 100,
        },
    )

    assert all_text_response.status_code == 200

    all_text_data = all_text_response.json()
    all_text_documents = all_text_data["items"]

    assert all_text_data["total"] == len(all_text_documents)
    assert all_text_data["limit"] == 100
    assert all_text_data["offset"] == 0

    first_page = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
        params={
            "source_type": "text",
            "limit": 1,
            "offset": 0,
        },
    )

    second_page = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
        params={
            "source_type": "text",
            "limit": 1,
            "offset": 1,
        },
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_page_data = first_page.json()
    second_page_data = second_page.json()

    assert first_page_data["total"] == all_text_data["total"]
    assert second_page_data["total"] == all_text_data["total"]

    assert first_page_data["limit"] == 1
    assert first_page_data["offset"] == 0

    assert second_page_data["limit"] == 1
    assert second_page_data["offset"] == 1

    assert (
        first_page_data["items"][0]["id"]
        == all_text_documents[0]["id"]
    )

    assert (
        second_page_data["items"][0]["id"]
        == all_text_documents[1]["id"]
    )

    assert all(
        document["id"] != user_b_document["id"]
        for document in all_text_documents
    )


def test_list_documents_pagination_validation(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-pagination-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    invalid_cases = [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ]

    for params in invalid_cases:
        response = client.get(
            "/api/v1/documents",
            headers=headers,
            params=params,
        )

        assert response.status_code == 422

def test_list_documents_offset_beyond_total(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-offset-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Pagination document",
            "content": "Pagination content",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    response = client.get(
        "/api/v1/documents",
        headers=headers,
        params={
            "limit": 20,
            "offset": 100,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["items"] == []
    assert data["total"] == 1
    assert data["limit"] == 20
    assert data["offset"] == 100

def test_list_documents_sorting(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-sorting-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    titles = [
        "Charlie document",
        "Alpha document",
        "Bravo document",
    ]

    for title in titles:
        response = client.post(
            "/api/v1/documents",
            headers=headers,
            json={
                "title": title,
                "content": f"Content for {title}",
                "source_type": "text",
            },
        )

        assert response.status_code == 201

    ascending_response = client.get(
        "/api/v1/documents",
        headers=headers,
        params={
            "sort_by": "title",
            "sort_order": "asc",
            "limit": 100,
        },
    )

    assert ascending_response.status_code == 200

    ascending_titles = [
        document["title"]
        for document in ascending_response.json()["items"]
    ]

    assert ascending_titles == sorted(ascending_titles)

    descending_response = client.get(
        "/api/v1/documents",
        headers=headers,
        params={
            "sort_by": "title",
            "sort_order": "desc",
            "limit": 100,
        },
    )

    assert descending_response.status_code == 200

    descending_titles = [
        document["title"]
        for document in descending_response.json()["items"]
    ]

    assert descending_titles == sorted(
        descending_titles,
        reverse=True,
    )


def test_list_documents_sorting_validation(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-sorting-validation-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    invalid_cases = [
        {
            "sort_by": "status",
        },
        {
            "sort_order": "random",
        },
    ]

    for params in invalid_cases:
        response = client.get(
            "/api/v1/documents",
            headers=headers,
            params=params,
        )

        assert response.status_code == 422