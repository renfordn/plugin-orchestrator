# agent-ux INTEROP

UI/UX rendering and events.

## Capabilities

### render_event

Render progress UI events.

Consumes:
- event_type: string
- event_data: object

Produces:
- rendered_html: string
- event_id: string
