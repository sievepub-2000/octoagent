# File Upload Feature

## Overview

OctopusAgent's backend provides multi-file upload support and can automatically convert Office documents and PDFs into Markdown.

## Key Features

- multi-file upload support
- automatic Markdown conversion for PDF, PowerPoint, Excel, and Word files
- thread-isolated storage directories
- automatic agent awareness of uploaded files
- file listing and file deletion support

## API Endpoints

### Upload files

```http
POST /api/threads/{thread_id}/uploads
```

Request body: `multipart/form-data`

- `files`: one or more files

### List uploaded files

```http
GET /api/threads/{thread_id}/uploads/list
```

### Delete an uploaded file

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

## Supported conversion formats

The following file types are converted to Markdown automatically:

- `.pdf`
- `.ppt`
- `.pptx`
- `.xls`
- `.xlsx`
- `.doc`
- `.docx`

## Agent integration

Uploaded files are surfaced to the agent with sandbox-visible virtual paths such as:

- `/mnt/user-data/uploads/document.pdf`
- `/mnt/user-data/uploads/document.md`

The agent can read them with tools such as `read_file`.

## Path model

- Agent-visible virtual path: `/mnt/user-data/uploads/...`
- Actual thread storage: `backend/.octopusagent/threads/{thread_id}/user-data/uploads/...`
- Front-end HTTP artifact path: `/api/threads/{thread_id}/artifacts/...`

## Limits

- Maximum upload size depends on the Nginx `client_max_body_size` setting.
- Uploads are isolated per thread.
- File paths are validated to prevent directory traversal.
