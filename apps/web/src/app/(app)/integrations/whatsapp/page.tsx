"use client";

import { Info, Loader2, MessageCircle, Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { IntegrationHeader, useIntegration } from "@/components/integrations/integration-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import { useIntegrationMutations } from "@/lib/api/hooks";

export default function WhatsAppPage() {
  const { integration } = useIntegration("whatsapp");
  const { configureWhatsApp } = useIntegrationMutations();
  const connected = integration?.status === "connected";
  const [form, setForm] = useState({
    phone_number_id: "",
    access_token: "",
    business_account_id: "",
    display_phone_number: "",
  });
  const [to, setTo] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await configureWhatsApp.mutateAsync({
        phone_number_id: form.phone_number_id.trim(),
        access_token: form.access_token.trim(),
        business_account_id: form.business_account_id.trim() || undefined,
        display_phone_number: form.display_phone_number.trim() || undefined,
      });
      setForm({ phone_number_id: "", access_token: "", business_account_id: "", display_phone_number: "" });
      toast.success("WhatsApp Business connected");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save");
    }
  }

  async function sendTest(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      await api("/whatsapp/messages", { method: "POST", body: { to, message } });
      toast.success("Message sent");
      setMessage("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <IntegrationHeader provider="whatsapp" icon={<MessageCircle className="size-7" />} />
      <Alert className="mb-4">
        <Info />
        <AlertTitle>Official WhatsApp Business Platform only</AlertTitle>
        <AlertDescription>
          Nexora uses Meta&apos;s Cloud API with a WhatsApp Business phone number. It cannot automate a personal
          WhatsApp account and does not use WhatsApp Web. Free-form messages only work within 24 hours of the
          recipient&apos;s last message. Outside that window Meta requires approved templates. Every message the
          assistant prepares needs your approval.
        </AlertDescription>
      </Alert>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {connected ? "Update credentials" : "Connect your business number"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={save} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="wa-phone-id">Phone number ID</Label>
                <Input
                  id="wa-phone-id"
                  inputMode="numeric"
                  value={form.phone_number_id}
                  onChange={(e) => setForm({ ...form, phone_number_id: e.target.value })}
                  placeholder="From Meta App > WhatsApp > API setup"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wa-token">Access token</Label>
                <Input
                  id="wa-token"
                  type="password"
                  autoComplete="off"
                  value={form.access_token}
                  onChange={(e) => setForm({ ...form, access_token: e.target.value })}
                  placeholder="System user token (encrypted at rest)"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="wa-waba">Business account ID</Label>
                  <Input
                    id="wa-waba"
                    inputMode="numeric"
                    value={form.business_account_id}
                    onChange={(e) => setForm({ ...form, business_account_id: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="wa-display">Display number</Label>
                  <Input
                    id="wa-display"
                    value={form.display_phone_number}
                    onChange={(e) => setForm({ ...form, display_phone_number: e.target.value })}
                    placeholder="+91…"
                  />
                </div>
              </div>
              <Button type="submit" disabled={configureWhatsApp.isPending || !integration?.available}>
                {configureWhatsApp.isPending && <Loader2 className="animate-spin" />} Save & connect
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Send a message</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={sendTest} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="wa-to">To (international format)</Label>
                <Input
                  id="wa-to"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  placeholder="+919876543210"
                  disabled={!connected}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wa-msg">Message</Label>
                <Textarea
                  id="wa-msg"
                  rows={3}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  disabled={!connected}
                />
              </div>
              <Button type="submit" disabled={!connected || sending || !to || !message}>
                {sending ? <Loader2 className="animate-spin" /> : <Send />} Send
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
