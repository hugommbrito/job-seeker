import {
  useChannels,
  useLinkTelegram,
  useTestTelegram,
  useUnlinkTelegram,
} from "@/api/notifications";
import { Button } from "@/components/ui/button";

export function TelegramSection() {
  const channels = useChannels();
  const link = useLinkTelegram();
  const unlink = useUnlinkTelegram();
  const test = useTestTelegram();
  const telegram = channels.data?.telegram;

  if (!telegram) return null;
  if (!telegram.available) {
    return <p className="text-sm text-muted-foreground">Telegram is not set up on this server.</p>;
  }
  const error = link.error ?? unlink.error ?? test.error;

  return (
    <div className="flex flex-col gap-3 text-sm">
      {telegram.linked ? (
        <>
          <p>
            {telegram.enabled
              ? "Linked. Reminders are pushed to your Telegram chat, outside quiet hours."
              : "Linked, but switched off: the bot could not reach the chat. Link it again."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate()}>
              Send a test
            </Button>
            <Button variant="ghost" size="sm" onClick={() => unlink.mutate()}>
              Unlink
            </Button>
            {!telegram.enabled && (
              <Button size="sm" onClick={() => link.mutate()}>
                Link again
              </Button>
            )}
          </div>
          {test.isSuccess && <p className="text-muted-foreground">Sent, unless it is quiet time.</p>}
        </>
      ) : (
        <>
          <p>Get reminders on your phone through the app's Telegram bot.</p>
          {link.data && telegram.linking ? (
            <p>
              <a href={link.data.url} target="_blank" rel="noopener noreferrer" className="underline">
                Open the bot in Telegram
              </a>{" "}
              and press Start. This page updates once the bot has your chat (within a minute). The
              link works for fifteen minutes.
            </p>
          ) : (
            <div>
              <Button size="sm" disabled={link.isPending} onClick={() => link.mutate()}>
                Link Telegram
              </Button>
            </div>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="text-destructive">
          {error.message}
        </p>
      )}
    </div>
  );
}
