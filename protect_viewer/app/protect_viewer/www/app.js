// Protect Viewer UI. All URLs are relative so the page works under the Ingress path.

const view = document.getElementById('view');
const title = document.getElementById('title');
const back = document.getElementById('back');
const banner = document.getElementById('banner');
const tabs = document.querySelectorAll('nav a');

const STATUS_INTERVAL = 30000;
const TYPE_LABELS = {
  person: 'Person',
  vehicle: 'Vehicle',
  animal: 'Animal',
  package: 'Package',
  licensePlate: 'License plate',
  face: 'Face',
};
const FILTER_TYPES = ['person', 'vehicle', 'animal', 'package'];

let cameras = [];

// Detections list state, kept while viewing a clip so going back doesn't reload it
const detections = {
  camera: '', type: '', events: [], next: undefined, loading: false, scroll: 0, generation: 0,
};
let observer = null;

function wsUrl(stream) {
  return new URL(`api/ws?src=${encodeURIComponent(stream)}`, document.baseURI);
}

function snapshotUrl(camera) {
  return `api/cameras/${encodeURIComponent(camera.id)}/snapshot?t=${Date.now()}`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function cameraName(id) {
  return cameras.find(c => c.id === id)?.name || 'Unknown camera';
}

function setChrome(text, showBack, tab) {
  title.textContent = text;
  back.hidden = !showBack;
  for (const link of tabs) link.classList.toggle('active', link.dataset.tab === tab);
  if (observer) {
    observer.disconnect();
    observer = null;
  }
}

// ---- Live ----

function player(stream, media) {
  const node = document.createElement('video-stream');
  node.mode = 'webrtc,mse';
  node.media = media;
  node.src = wsUrl(stream);
  return node;
}

// The player creates its <video> once it is attached to the document.
function setupVideos(controls) {
  for (const node of view.querySelectorAll('video-stream')) {
    if (!node.video) continue;
    node.video.controls = controls;
    node.video.poster = node.dataset.poster || '';
  }
}

function problem(camera) {
  if (!camera.connected) return 'Camera is offline';
  if (!camera.streams) return 'RTSP is not enabled for this camera in Protect';
  return null;
}

function renderGrid() {
  setChrome('Cameras', false, 'live');
  view.replaceChildren();

  if (!cameras.length) {
    view.append(el('div', 'empty', 'No cameras found.'));
    return;
  }

  const grid = el('div', 'grid');
  for (const camera of cameras) {
    const tile = el('div', 'tile');
    tile.dataset.id = camera.id;
    tile.style.backgroundImage = `url("${snapshotUrl(camera)}")`;
    tile.addEventListener('click', () => { location.hash = `#/camera/${camera.id}`; });

    const issue = problem(camera);
    if (issue) {
      tile.append(el('div', 'notice', issue));
    } else {
      const node = player(camera.streams.grid, 'video');
      node.dataset.poster = snapshotUrl(camera);
      tile.append(node);
    }

    const label = el('div', 'label');
    label.append(el('span', camera.connected ? 'dot' : 'dot off'), camera.name);
    tile.append(label);
    grid.append(tile);
  }
  view.append(grid);
  setupVideos(false);
}

function renderCamera(id) {
  const camera = cameras.find(c => c.id === id);
  if (!camera) {
    location.hash = '';
    return;
  }
  setChrome(camera.name, true, 'live');
  view.replaceChildren();

  const single = el('div', 'single');
  const issue = problem(camera);
  if (issue) {
    single.append(el('div', 'notice', issue));
  } else {
    const node = player(camera.streams.main, 'video,audio');
    node.dataset.poster = snapshotUrl(camera);
    single.append(node);
  }
  view.append(single);
  setupVideos(true);
}

// ---- Detections ----

function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
}

function timeLabel(ms) {
  return new Date(ms).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function durationLabel(event) {
  if (!event.end) return 'now';
  const seconds = Math.max(1, Math.round((event.end - event.start) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function typesLabel(event) {
  return event.types.map(t => TYPE_LABELS[t] || t).join(' · ');
}

// Protect describes vehicles in lower case, like "blue suv"
function detailsLabel(event) {
  const text = event.details.join(', ').replace(/\bsuv\b/g, 'SUV');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function resetDetections() {
  detections.events = [];
  detections.next = undefined;
  detections.scroll = 0;
  detections.loading = false;
  detections.generation += 1; // results for the old filters are dropped
}

function filters() {
  const bar = el('div', 'filters');

  const select = el('select');
  select.setAttribute('aria-label', 'Camera');
  select.append(new Option('All cameras', ''));
  for (const camera of cameras) select.append(new Option(camera.name, camera.id));
  select.value = detections.camera;
  select.addEventListener('change', () => {
    detections.camera = select.value;
    resetDetections();
    renderDetections();
  });
  bar.append(select);

  for (const type of ['', ...FILTER_TYPES]) {
    const chip = el('button', 'chip', type ? TYPE_LABELS[type] : 'All');
    chip.classList.toggle('active', detections.type === type);
    chip.addEventListener('click', () => {
      if (detections.type === type) return;
      detections.type = type;
      resetDetections();
      renderDetections();
    });
    bar.append(chip);
  }
  return bar;
}

function eventCard(event) {
  const card = el('a', 'event');
  card.href = `#/event/${event.id}`;
  card.addEventListener('click', () => { detections.scroll = window.scrollY; });

  const thumb = el('div', 'thumb');
  const img = el('img');
  img.loading = 'lazy';
  img.alt = '';
  img.src = `api/events/${encodeURIComponent(event.id)}/thumbnail`;
  thumb.append(img, el('span', 'time', timeLabel(event.start)), el('span', 'duration', durationLabel(event)));

  const meta = el('div', 'meta');
  meta.append(el('span', 'camera', cameraName(event.camera)), el('span', 'types', typesLabel(event)));
  card.append(thumb, meta);
  if (event.details.length) card.append(el('div', 'details', detailsLabel(event)));
  return card;
}

function renderEventList(list) {
  list.replaceChildren();
  let day = null;
  let group = null;
  for (const event of detections.events) {
    const date = new Date(event.start);
    if (date.toDateString() !== day) {
      day = date.toDateString();
      list.append(el('h2', 'day', dayLabel(date)));
      group = el('div', 'events');
      list.append(group);
    }
    group.append(eventCard(event));
  }
}

function renderFooter(footer) {
  if (detections.loading) footer.textContent = 'Loading…';
  else if (detections.next === null && !detections.events.length) footer.textContent = 'No detections found.';
  else if (detections.next === null) footer.textContent = 'That\'s everything Protect has.';
  else footer.textContent = '';
}

async function loadMore(list, footer) {
  if (detections.loading || detections.next === null) return;
  detections.loading = true;
  renderFooter(footer);
  const params = new URLSearchParams();
  if (detections.camera) params.set('camera', detections.camera);
  if (detections.type) params.set('type', detections.type);
  if (detections.next) params.set('before', detections.next);
  const generation = detections.generation;
  let ok = false;
  try {
    const resp = await fetch(`api/events?${params}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (generation !== detections.generation) return;
    detections.events.push(...data.events);
    detections.next = data.next;
    renderEventList(list);
    ok = true;
  } catch (err) {
    if (generation === detections.generation) showBanner(`Loading detections failed: ${err.message}`);
  } finally {
    if (generation === detections.generation) {
      detections.loading = false;
      renderFooter(footer);
      // Observing again fires right away if the footer is still in view.
      // Not after an error, or a failing console would be asked again and again.
      if (ok && observer) {
        observer.unobserve(footer);
        observer.observe(footer);
      }
    }
  }
}

function renderDetections() {
  setChrome('Detections', false, 'detections');
  const list = el('div', 'event-list');
  const footer = el('div', 'list-footer');
  view.replaceChildren(filters(), list, footer);
  renderEventList(list);
  renderFooter(footer);
  window.scrollTo(0, detections.scroll);

  // Load the next page whenever the bottom of the list comes into view
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) loadMore(list, footer);
  }, { rootMargin: '600px' });
  observer.observe(footer);
}

function renderEvent(id) {
  const event = detections.events.find(e => e.id === id);
  setChrome(event ? cameraName(event.camera) : 'Detection', true, 'detections');

  const clip = el('div', 'clip');
  const video = el('video');
  video.controls = true;
  video.playsInline = true;
  const status = el('div', 'notice', 'Loading clip…');
  clip.append(video, status);

  video.addEventListener('loadeddata', () => status.remove());
  video.addEventListener('error', () => {
    const hevc = video.canPlayType('video/mp4; codecs="hvc1"');
    status.textContent = hevc
      ? 'This clip could not be loaded.'
      : 'This browser can\'t play the cameras\' H.265 video. Safari and Chrome can.';
  });
  video.src = `api/events/${encodeURIComponent(id)}/clip`;
  video.play().catch(() => {
    video.muted = true;
    video.play().catch(() => {});
  });

  view.replaceChildren(clip);
  if (event) {
    const info = el('div', 'clip-info');
    const when = new Date(event.start);
    info.append(
      el('div', 'clip-title', typesLabel(event) || 'Detection'),
      el('div', 'clip-sub', `${dayLabel(when)} ${timeLabel(event.start)} · ${durationLabel(event)}`),
    );
    if (event.details.length) info.append(el('div', 'clip-sub', detailsLabel(event)));
    view.append(info);
  }
}

// ---- Routing and refresh ----

function route() {
  const hash = location.hash;
  let match;
  if ((match = hash.match(/^#\/camera\/(.+)$/))) renderCamera(decodeURIComponent(match[1]));
  else if ((match = hash.match(/^#\/event\/(.+)$/))) renderEvent(decodeURIComponent(match[1]));
  else if (hash === '#/detections') renderDetections();
  else renderGrid();
}

function onLiveView() {
  return !location.hash.startsWith('#/detections') && !location.hash.startsWith('#/event/');
}

function showBanner(text) {
  banner.textContent = text || '';
  banner.hidden = !text;
}

// Only re-render when something that changes the players differs, so streams keep running.
function signature(list) {
  return JSON.stringify(list.map(c => [c.id, c.name, c.connected, c.streams]));
}

async function refresh(initial) {
  try {
    const resp = await fetch('api/cameras', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    showBanner(data.error);
    document.body.classList.toggle('hide-stream-type', !data.show_stream_type);
    const changed = signature(data.cameras) !== signature(cameras);
    cameras = data.cameras;
    if (initial || (changed && onLiveView())) route();
  } catch (err) {
    showBanner(`Cannot reach the add-on: ${err.message}`);
  }
}

back.addEventListener('click', () => {
  if (history.length > 1) history.back();
  else location.hash = location.hash.startsWith('#/event/') ? '#/detections' : '';
});
window.addEventListener('hashchange', route);

refresh(true);
setInterval(() => refresh(false), STATUS_INTERVAL);
