import { http } from "./http";

type StreamChannel = "chat_ask" | "alerts" | "ingest_job";

export async function mintStreamTicket(
  channel: StreamChannel,
  resourceId: string
): Promise<string | null> {
  try {
    const { ticket } = await http<{ ticket: string }>(
      "/api/v1/streams/ticket",
      {
        method: "POST",
        body: JSON.stringify({ channel, resource_id: resourceId }),
        skipAuthRedirect: true,
      }
    );
    return ticket;
  } catch {
    return null;
  }
}
