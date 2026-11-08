// ---------------------------------------------------------------------------------------------
// how a person looks: an optional picture (cropped and re-encoded here, then public) and an optional built face.
// Agents keep their own faces; this is the owner's. The same editor is in onboarding and Settings.
// ---------------------------------------------------------------------------------------------

const PICTURE_FILE = /^image\/(png|jpeg|webp|gif|bmp|avif)$/   // rasters only: an SVG is never drawn or sent
const PICTURE_FILE_MAX = 25 * 1024 * 1024

// Crop (centre, zoom, drag or arrow keys) and preview a chosen file on the 256 pixel canvas the picture is made from.
// onUse(dataUri) gets the re-encoded result; the original file is only ever read by this page.
function AvatarCropper(props) {
  const [img, setImg] = useState(null)
  const [err, setErr] = useState('')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const canvas = useRef(null)
  const drag = useRef(null)
  const ref = useEnter(true)
  useEffect(() => {
    let live = true
    let url = ''
    const done = (src, w, h) => { if (live) setImg({ src, w, h }) }
    const fallback = () => {
      try {
        url = URL.createObjectURL(props.file)
        const im = new Image()
        im.onload = () => done(im, im.naturalWidth, im.naturalHeight)
        im.onerror = () => { if (live) setErr('Ninsei could not read that file as a picture.') }
        im.src = url
      } catch (_) { if (live) setErr('Ninsei could not read that file as a picture.') }
    }
    if (typeof createImageBitmap === 'function') createImageBitmap(props.file).then(b => done(b, b.width, b.height), fallback)
    else fallback()
    return () => { live = false; if (url) URL.revokeObjectURL(url) }
  }, [props.file])
  useEffect(() => {
    const c = canvas.current
    if (!img || !c) return
    const g = c.getContext('2d')
    const r = avatarCrop(img.w, img.h, zoom, pan.x, pan.y)
    g.fillStyle = '#ffffff'
    g.fillRect(0, 0, AVATAR_PX, AVATAR_PX)
    g.imageSmoothingEnabled = true
    g.imageSmoothingQuality = 'high'
    g.drawImage(img.src, r.sx, r.sy, r.sw, r.sh, 0, 0, AVATAR_PX, AVATAR_PX)
  }, [img, zoom, pan.x, pan.y])
  const use = () => {
    const uri = canvas.current ? encodeAvatar(canvas.current, AVATAR_BYTES) : null
    if (!uri) { setErr('That picture would not shrink small enough. Zoom in, or try another one.'); return }
    props.onUse(uri)
  }
  const move = (dx, dy) => setPan(p => ({ x: clamp(p.x + dx, -1, 1), y: clamp(p.y + dy, -1, 1) }))
  const onKey = e => {
    const step = 0.12
    if (e.key === 'ArrowLeft') move(-step, 0)
    else if (e.key === 'ArrowRight') move(step, 0)
    else if (e.key === 'ArrowUp') move(0, -step)
    else if (e.key === 'ArrowDown') move(0, step)
    else if (e.key === '+' || e.key === '=') setZoom(z => clamp(z + 0.1, 1, 3))
    else if (e.key === '-') setZoom(z => clamp(z - 0.1, 1, 3))
    else return
    e.preventDefault()
  }
  return jsxs('div', { className: 'h-crop', ref, children: [
    err && jsx(Notice, { icon: 'warning', role: 'alert', children: err }),
    !img && !err && jsx('div', { className: 'h-faint h-small', children: 'Reading the picture…' }),
    img && jsxs('div', { className: 'h-row h-crop-row', children: [
      jsx('div', { className: 'h-crop-view', tabIndex: 0, role: 'group', 'aria-label': 'Picture crop. Arrow keys move it, plus and minus zoom.', onKeyDown: onKey,
        onPointerDown: e => { drag.current = { x: e.clientX, y: e.clientY, p: pan }; try { e.currentTarget.setPointerCapture(e.pointerId) } catch (_) { /* not capturable */ } },
        onPointerMove: e => { const d = drag.current; if (d) setPan({ x: clamp(d.p.x - (e.clientX - d.x) / 80, -1, 1), y: clamp(d.p.y - (e.clientY - d.y) / 80, -1, 1) }) },
        onPointerUp: () => { drag.current = null }, onPointerCancel: () => { drag.current = null },
        children: jsx('canvas', { ref: canvas, width: AVATAR_PX, height: AVATAR_PX, 'aria-hidden': true }) }),
      jsxs('div', { className: 'h-col', style: { gap: 8, minWidth: 0 }, children: [
        jsxs('label', { className: 'h-faint h-small', children: ['Zoom ', jsx('input', { type: 'range', className: 'h-hue', min: 1, max: 3, step: 0.05, value: zoom, 'aria-label': 'Zoom',
          onChange: e => setZoom(Number(e.target.value)) })] }),
        jsx('div', { className: 'h-faint h-tiny', children: 'Drag the picture, or use the arrow keys, to move it.' }),
        jsxs('div', { className: 'h-actions', children: [
          jsx(K.Button, { variant: 'primary', size: 'sm', onClick: use, disabled: !!props.busy, children: props.useLabel || 'Use this picture' }),
          jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: props.onCancel, children: 'Cancel' })
        ] })
      ] })
    ] })
  ] })
}

// How you look. The pixel avatar builder comes first; a photo is the opt-in alternative (it shows first where
// pictures are on, and the avatar stands in where they're off). Props: pk, name; avatar (a clean avatar or null) and
// onAvatar(avatar|null); face (an older built face, or null) and onFace(null) to drop it; art ({av?, avatar?, face?}:
// what shows now); staged (a picture waiting for Save, onboarding) or null; onPicture(uri) with a data URI, or '' to
// take it away; hasPicture; busy; stage (true in onboarding: a picture is held until setup finishes).
function PersonLook(props) {
  const [file, setFile] = useState(null)
  const [note, setNote] = useState('')
  const input = useRef(null)
  const pick = e => {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f) return
    if (!PICTURE_FILE.test(f.type)) { setNote('Choose a PNG, JPEG, WebP or GIF picture.'); return }
    if (f.size > PICTURE_FILE_MAX) { setNote('That file is over 25 MB. Choose a smaller picture.'); return }
    setNote('')
    setFile(f)
  }
  const used = uri => { setFile(null); props.onPicture(uri) }
  const has = !!(props.staged || props.hasPicture)
  const shown = props.staged ? Object.assign({}, props.art || {}, { uri: props.staged }) : props.art
  return jsxs('div', { className: 'h-col h-look', style: { gap: 12 }, children: [
    jsx(AvatarEditor, { id: props.id, value: props.avatar, name: props.name, onChange: props.onAvatar }),
    jsx('div', { className: 'h-hint', children: props.avatar
      ? 'Public like your name: your avatar goes out with your face settings to public Nostr relays, and anyone in your rooms sees it.'
      : 'Not set yet: until you change something here, people see your initial. Once set it is public like your name.' }),
    jsxs('div', { className: 'h-actions', children: [
      props.avatar && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => props.onAvatar(null), children: 'Use my initial instead' }),
      props.face && jsx(K.Button, { variant: 'ghost', size: 'sm', onClick: () => props.onFace(null), children: 'Remove my older face' })
    ] }),
    jsxs('div', { className: 'h-col', style: { gap: 8 }, children: [
      jsx('div', { className: 'h-label', style: { fontSize: 12, fontWeight: 600, color: 'var(--h-fg2)' }, children: 'Photo (optional)' }),
      jsxs('div', { className: 'h-row', style: { gap: 14, alignItems: 'flex-start' }, children: [
        has && jsx(PersonMark, { pk: props.pk, name: props.name || 'You', size: 48, art: shown || null }),
        jsxs('div', { className: 'h-col', style: { gap: 8, minWidth: 0 }, children: [
          jsxs('div', { className: 'h-actions', children: [
            jsx(K.Button, { variant: 'secondary', size: 'sm', disabled: !!props.busy, onClick: () => input.current && input.current.click(),
              children: has ? 'Change photo' : 'Use a photo instead' }),
            has && jsx(K.Button, { variant: 'ghost', size: 'sm', disabled: !!props.busy, onClick: () => { setFile(null); props.onPicture('') }, children: 'Remove photo' }),
            jsx('input', { type: 'file', ref: input, accept: 'image/png,image/jpeg,image/webp,image/gif', style: { display: 'none' }, tabIndex: -1, 'aria-hidden': true, onChange: pick })
          ] }),
          note && jsx('div', { className: 'h-hint h-err', role: 'alert', children: note }),
          jsx('div', { className: 'h-hint', children: props.stage
            ? 'A photo is shown instead of your avatar. It is published when you finish setup.'
            : 'A photo is shown instead of your avatar, for people who have pictures on.' })
        ] })
      ] }),
      file && jsx(AvatarCropper, { file, onUse: used, onCancel: () => setFile(null), busy: props.busy,
        useLabel: props.stage ? 'Use this picture' : 'Use and publish' }),
      jsxs('div', { className: 'h-hint', children: [
        'Public and permanent: your picture goes to public Nostr relays, where anyone can see it, and relays or other apps may keep old pictures forever, even after you remove it. ',
        'Ninsei crops it to a square, shrinks it to 256 pixels and re-encodes it on this computer, which drops EXIF details such as GPS location and camera model. The original file is never uploaded. People who turn pictures off see your avatar or initial instead.'
      ] })
    ] })
  ] })
}
