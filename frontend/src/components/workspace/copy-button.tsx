import { CheckIcon, CopyIcon } from "lucide-react";
import { useCallback, useState, type ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import { copyTextToClipboard } from "@/lib/clipboard";

export function CopyButton({
  clipboardData,
  ...props
}: ComponentProps<typeof Button> & {
  clipboardData: string;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    try {
      await copyTextToClipboard(clipboardData);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy message text", error);
    }
  }, [clipboardData]);

  const label = t.clipboard.copyToClipboard;

  return (
    <Button
      aria-label={label}
      size="icon-sm"
      title={label}
      type="button"
      variant="ghost"
      onClick={handleCopy}
      disabled={!clipboardData}
      {...props}
    >
      {copied ? (
        <CheckIcon className="text-green-500" size={12} />
      ) : (
        <CopyIcon size={12} />
      )}
    </Button>
  );
}
