import { text } from "./format.js";
import {
  QZONE_MEDIA_LIMIT,
  dataUrlToBase64Source,
  postId,
  qzoneMediaFileKind,
  readFileAsDataUrl,
} from "./zonekit.js";

export function createQzoneComposer({
  state,
  elements: el,
  apiPost,
  setNotice,
  updateButtons,
  renderQzone,
  reloadStatus,
  loadQzoneFeed,
} = {}) {
  function previewSource(item = {}) {
    const source = text(item.preview || item.source).trim();
    if (!source) return "";
    if (source.startsWith("base64://")) {
      return `data:${text(item.mime_type).trim() || "image/jpeg"};base64,${source.slice("base64://".length)}`;
    }
    return source;
  }

  function renderComposerMedia() {
    if (!el.qzoneMediaStrip) return;
    const nodes = state.qzoneMedia.map((item, index) => {
      const chip = document.createElement("div");
      chip.className = "qzone-media-chip is-image";
      const thumb = document.createElement("span");
      thumb.className = "qzone-media-thumb";
      const src = previewSource(item);
      if (src) {
        const img = document.createElement("img");
        img.alt = "";
        img.src = src;
        thumb.append(img);
      } else {
        thumb.textContent = "🌸";
      }
      const name = document.createElement("span");
      name.className = "qzone-media-name";
      name.textContent = text(item.name).trim() || `图片 ${index + 1}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "qzone-media-remove";
      remove.dataset.qzoneMediaIndex = String(index);
      remove.setAttribute("aria-label", `移除第 ${index + 1} 张图片`);
      remove.textContent = "×";
      chip.append(thumb, name, remove);
      return chip;
    });
    el.qzoneMediaStrip.replaceChildren(...nodes);
    el.qzoneMediaStrip.hidden = !nodes.length;
  }

  async function uploadQzoneFiles(files) {
    const uploads = [...files]
      .map((file) => ({ file, kind: qzoneMediaFileKind(file) }))
      .filter((item) => item.kind === "image");
    if (!uploads.length) return;
    state.qzoneMediaReading = true;
    updateButtons();
    try {
      for (const { file } of uploads) {
        if (state.qzoneMedia.length >= QZONE_MEDIA_LIMIT) {
          setNotice(`最多只能添加 ${QZONE_MEDIA_LIMIT} 张图片`);
          break;
        }
        try {
          const mediaData = await readFileAsDataUrl(file);
          const source = dataUrlToBase64Source(mediaData);
          if (!source) throw new Error("图片读取失败");
          state.qzoneMedia.push({
            kind: "image",
            name: file.name || `图片 ${state.qzoneMedia.length + 1}`,
            source,
            preview: mediaData,
            size: file.size || 0,
            mime_type: file.type || "image/jpeg",
          });
          renderComposerMedia();
        } catch (error) {
          setNotice(error.message || "图片读取失败", "error");
        }
      }
    } finally {
      state.qzoneMediaReading = false;
      updateButtons();
    }
  }

  async function publishQzone(event) {
    event.preventDefault();
    const content = text(el.qzonePublishText?.value).trim();
    const media = state.qzoneMedia
      .map((item) => ({
        kind: "image",
        name: text(item.name).trim(),
        source: text(item.source).trim(),
        mime_type: text(item.mime_type).trim(),
        size: Number(item.size || 0),
      }))
      .filter((item) => item.source);
    if (!content && !media.length) {
      setNotice("说说内容或媒体不能为空", "error");
      return;
    }
    state.qzonePublishing = true;
    updateButtons();
    try {
      setNotice(media.length ? "正在处理图片并发布 QQ 空间说说，请稍候..." : "正在发布 QQ 空间说说，请稍候...", "info");
      const data = await apiPost("page/qzone/publish", { text: content, media }, 65000);
      const item = data.item || data.post;
      if (item) state.qzoneItems = [item, ...state.qzoneItems.filter((old) => postId(old) !== postId(item))].slice(0, 10);
      if (el.qzonePublishText) el.qzonePublishText.value = "";
      state.qzoneMedia = [];
      setNotice("说说已发布", "success");
      renderQzone();
      await reloadStatus?.({ quiet: true });
      await loadQzoneFeed({ quiet: true });
    } catch (error) {
      setNotice(error.message || "说说发布失败", "error");
    } finally {
      state.qzonePublishing = false;
      updateButtons();
    }
  }

  return {
    publishQzone,
    renderComposerMedia,
    uploadQzoneFiles,
  };
}
