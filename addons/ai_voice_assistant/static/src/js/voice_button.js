import { Component, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export class VoiceButton extends Component {
    static template = "ai_voice_assistant.VoiceButton";
    static props = [];

    setup() {
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.orm = useService("orm");

        this.state = useState({
            isRecording: false,
            isProcessing: false,
        });

        this.mediaRecorder = null;
        this.audioChunks = [];
        this.activeStream = null;

        onWillUnmount(() => this._cleanup());
    }

    async toggleRecording() {
        if (this.state.isRecording) {
            this._stopRecording();
        } else {
            await this._startRecording();
        }
    }

    async _startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.notification.add(_t("المتصفح لا يدعم تسجيل الصوت"), { type: "danger" });
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.activeStream = stream;
            this.audioChunks = [];

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : "audio/webm";

            this.mediaRecorder = new MediaRecorder(stream, { mimeType });
            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };
            this.mediaRecorder.onstop = () => this._processRecording();
            this.mediaRecorder.start(250);
            this.state.isRecording = true;
        } catch (err) {
            this.notification.add(
                _t("لا يمكن الوصول للميكروفون: ") + err.message,
                { type: "danger" }
            );
        }
    }

    _stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
            this.mediaRecorder.stop();
        }
        this.state.isRecording = false;
    }

    async _processRecording() {
        this.state.isProcessing = true;
        this._cleanup();

        try {
            const audioBlob = new Blob(this.audioChunks, { type: "audio/webm" });
            const audioBase64 = await this._blobToBase64(audioBlob);
            // Strip the data:audio/...;base64, prefix
            const base64Data = audioBase64.split(",")[1];

            const { resModel, resId } = this._getCurrentContext();

            const result = await rpc("/ai_voice/process", {
                audio_base64: base64Data,
                res_model: resModel,
                res_id: resId || null,
            });

            if (result.success) {
                await this._executeAIAction(result.data, resModel, resId);
            } else {
                this.notification.add(
                    _t("خطأ من سيرفر الذكاء الاصطناعي: ") + (result.error || ""),
                    { type: "danger", sticky: true }
                );
            }
        } catch (err) {
            this.notification.add(_t("خطأ أثناء المعالجة: ") + err.message, {
                type: "danger",
            });
        } finally {
            this.state.isProcessing = false;
        }
    }

    _getCurrentContext() {
        const controllers = this.env.services?.action?.currentController;
        if (!controllers) return { resModel: "", resId: null };

        const action = controllers.action || {};
        const resModel = action.res_model || "";
        const resId = controllers.currentState?.resId || action.res_id || null;
        return { resModel, resId };
    }

    async _executeAIAction(data, resModel, resId) {
        const { intent, extracted_data, report_instruction, feedback_message } = data;

        if (feedback_message) {
            this.notification.add(feedback_message, {
                type: "success",
                autocloseDelay: 6000,
            });
        }

        if (!resModel) return;

        if (intent === "create") {
            // Resolve human-readable names to IDs before opening form
            const resolved = await this._resolveFieldNames(resModel, extracted_data);
            const context = {};
            for (const [key, val] of Object.entries(resolved)) {
                context[`default_${key}`] = val;
            }
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: resModel,
                views: [[false, "form"]],
                target: "current",
                context,
            });
        } else if (intent === "update" && resId) {
            const resolved = await this._resolveFieldNames(resModel, extracted_data);
            // Write only scalar and many2one fields directly
            const writeVals = Object.fromEntries(
                Object.entries(resolved).filter(([, v]) => !Array.isArray(v))
            );
            if (Object.keys(writeVals).length) {
                await this.orm.write(resModel, [resId], writeVals);
                // Trigger view reload
                const currentController = this.actionService.currentController;
                if (currentController?.reload) {
                    await currentController.reload();
                } else {
                    // Fallback: reload the whole action
                    await this.actionService.restore();
                }
            }
        } else if (intent === "report") {
            if (report_instruction) {
                this.notification.add(report_instruction, {
                    type: "info",
                    sticky: true,
                    title: _t("تقرير مُنشأ بالذكاء الاصطناعي"),
                });
            }
            // Trigger PDF report if a standard report action exists
            try {
                await this.actionService.doAction(
                    "report",
                    { resIds: resId ? [resId] : [] }
                );
            } catch {
                // Report action not available — notification already shown
            }
        } else if (intent === "navigate") {
            const targetId = extracted_data?.res_id;
            if (targetId && resModel) {
                await this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: resModel,
                    res_id: targetId,
                    views: [[false, "form"]],
                    target: "current",
                });
            }
        }
    }

    async _resolveFieldNames(resModel, fieldValues) {
        if (!fieldValues || !Object.keys(fieldValues).length) return {};
        try {
            return await rpc("/ai_voice/resolve_names", {
                res_model: resModel,
                field_values: fieldValues,
            });
        } catch {
            return fieldValues;
        }
    }

    _blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    _cleanup() {
        if (this.activeStream) {
            this.activeStream.getTracks().forEach((t) => t.stop());
            this.activeStream = null;
        }
    }
}

registry.category("systray").add(
    "ai_voice_button",
    { Component: VoiceButton },
    { sequence: 10 }
);
