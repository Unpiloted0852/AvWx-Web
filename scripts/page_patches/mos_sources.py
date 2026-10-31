"""MOS panel: real station forecasts instead of guessed ceilings. US airports get the NWS
LAMP (hourly, 25 h) and NBM (3-hourly, 72 h) forecasts from the Iowa Environmental Mesonet;
elsewhere DWD's MOSMIX station forecast (via Bright Sky) with the raw ICON and GFS models for
comparison. No ceiling is invented from cloud cover any more: sources without a ceiling forecast
say so, and their colour comes from visibility only. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('async function _fetchMos(icao, lat, lon, model) {' in l for l in lines): sys.exit('already applied')

def find_run(run, start=0):
    run = [r.strip() for r in run]
    hits = [i for i in range(start, len(lines) - len(run) + 1)
            if all(lines[i + k].strip() == run[k] for k in range(len(run)))]
    if len(hits) != 1: sys.exit(f'{len(hits)} matches for {run[0]!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]
def replace_run(run, new, start=0):
    i = find_run(run, start)
    pad = indent(i)
    lines[i:i + len(run)] = [pad + l if l else l for l in new]
    return i

# The sources, chosen per airport
replace_run(["const _MOS_MODELS    = ['ECMWF','ICON','GFS'];"], '''// Forecast sources. US airports: the NWS station forecasts LAMP (hourly, next 25 h) and NBM
// (3-hourly, 72 h), from the Iowa Environmental Mesonet. Elsewhere: DWD's MOSMIX station
// forecast (via Bright Sky), with the raw ICON and GFS models (Open-Meteo) to compare.
const _MOS_SOURCES_US    = ['LAMP','NBM','MOSMIX'];
const _MOS_SOURCES_WORLD = ['MOSMIX','ICON','GFS'];
let _MOS_MODELS = _MOS_SOURCES_WORLD;

function _mosIsUs(icao) {
    const s = cachedStationMap ? cachedStationMap.get(icao) : null;
    return s ? ['US', 'PR', 'GU', 'VI', 'AS', 'MP'].includes(s.country) : /^(K|P[AGHW]|TJ|TI)/.test(icao);
}'''.split('\n'))

# Open-Meteo: no ceiling guessed from cloud cover
replace_run(['const cigFt      = lowCov === null ? null', ': lowCov >= 88 ? 800', ': lowCov >= 63 ? 1800',
             ': lowCov >= 38 ? 3500', ': null;'],
            ["const cigFt      = null;   // the models give cloud cover, not a ceiling height: none is guessed"])

# The new fetchers, before _fetchMosOpenMeteo
i = find_run(['async function _fetchMosOpenMeteo(lat, lon, model) {'])
lines[i:i] = r'''// One source's forecast for an airport, as timeline blocks; blocks.note says what it is
async function _fetchMos(icao, lat, lon, model) {
    if (model === 'LAMP' || model === 'NBM') return _fetchMosIem(icao, model);
    if (model === 'MOSMIX') return _fetchMosMosmix(lat, lon);
    const blocks = await _fetchMosOpenMeteo(lat, lon, model);
    blocks.forEach(b => { b.cigLong = 'Not forecast'; });
    blocks.note = `Raw ${model} model output for this spot (Open-Meteo), not a station forecast. It has no ceiling, so the colour comes from visibility only.`;
    return blocks;
}

// LAMP / NBM from the Iowa Environmental Mesonet (station forecasts, temperatures in °F)
async function _fetchMosIem(icao, model) {
    const resp = await fetch(`https://mesonet.agron.iastate.edu/api/1/mos.json?station=${encodeURIComponent(icao)}&model=${model === 'LAMP' ? 'LAV' : 'NBS'}`);
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok || !Array.isArray(json.data) || !json.data.length) throw new Error(`no ${model} forecast for ${icao}`);
    const latest = json.data.reduce((m, r) => r.runtime_utc > m ? r.runtime_utc : m, '');
    const fToC = f => f === null || f === undefined ? null : (f - 32) * 5 / 9;
    const order = ['LIFR', 'IFR', 'MVFR', 'VFR'];
    const worse = (a, b) => !a ? (b || 'UNKN') : !b ? a : order[Math.min(order.indexOf(a), order.indexOf(b))];
    const now = Date.now(), blocks = [];
    for (const r of json.data) {
        if (r.runtime_utc !== latest) continue;
        const time = r.ftime_utc.slice(0, 16) + ':00Z';
        const t = Date.parse(time);
        if (t < now - 3600000 || t > now + 72 * 3600000) continue;
        const b = { time, windDir: r.wdr ?? null, windSpd: r.wsp ?? null, gust: r.gst || null, precipPct: null, precip: null,
            cigFt: null, visSm: null, lowCov: null, midCov: null, highCov: null, totalCov: null, rh: null, slp: null,
            weatherCode: null, tmp: fToC(r.tmp), dpt: fToC(r.dpt) };
        if (model === 'LAMP') {
            // Ceiling and visibility come as categories
            const cig = ['', '<200', '200–400', '500–900', '1000–1900', '2000–3000', '3100–6500', '6600–12000', '>12000'][r.cig] || '';
            const vis = ['', '<½', '½–<1', '1–<2', '2–<3', '3–5', '6', '>6'][r.vis] || '';
            b.cat = worse([null, 'LIFR', 'LIFR', 'IFR', 'MVFR', 'MVFR', 'VFR', 'VFR', 'VFR'][r.cig], [null, 'LIFR', 'LIFR', 'IFR', 'IFR', 'MVFR', 'VFR', 'VFR'][r.vis]);
            b.cigShort = cig ? (r.cig === 8 ? 'none' : `${cig}'`) : '--';
            b.cigLong = cig ? (r.cig === 8 ? 'None, or above 12,000 ft' : `${cig} ft AGL`) : '--';
            b.visShort = vis ? `${vis}sm` : '--';
            b.visLong = vis ? `${vis} SM` : '--';
            b.precipPct = r.ppo ?? null;
            b.thunderPct = r.lp1 ?? null;
            b.skyText = { CL: 'Clear', FW: 'Few', SC: 'Scattered', BK: 'Broken', OV: 'Overcast' }[String(r.cld || '').trim()] || null;
            b.wxText = { FG: 'Fog', BR: 'Mist', HZ: 'Haze', BL: 'Blowing snow/dust' }[String(r.obv || '').trim()] || null;
        } else {
            // NBM: ceiling in hundreds of feet (-88: none), visibility in tenths of a mile
            b.cigFt = r.cig > 0 ? r.cig * 100 : null;
            b.visSm = r.vis !== null && r.vis !== undefined && r.vis >= 0 ? r.vis / 10 : null;
            if (r.cig === -88) { b.cigShort = 'none'; b.cigLong = 'None'; }
            b.cat = _mosCat(r.cig === -88 ? 99999 : b.cigFt, b.visSm, null, null);
            b.totalCov = r.sky ?? null;
            if (r.p06 !== null && r.p06 !== undefined) { b.precipPct = r.p06; b.ppLong = `${Math.round(r.p06)}% in 6 h`; }
            b.thunderPct = r.t03 ?? null;
            b.cloudBase = r.lcb > 0 ? `${(r.lcb * 100).toLocaleString()} ft` : null;
        }
        blocks.push(b);
    }
    blocks.note = model === 'LAMP'
        ? 'LAMP: the NWS hourly aviation forecast for this airport (next 25 h), updated every hour. Ceiling and visibility come as ranges. Source: Iowa Environmental Mesonet.'
        : 'NBM: the NWS National Blend of Models forecast for this airport, every 3 hours out to 72 h. Source: Iowa Environmental Mesonet.';
    return blocks;
}

// MOSMIX, DWD's station forecast, via Bright Sky (wind in km/h, visibility in metres)
async function _fetchMosMosmix(lat, lon) {
    const hour = t => new Date(t).toISOString().slice(0, 13) + ':00';
    const resp = await fetch(`https://api.brightsky.dev/weather?lat=${lat}&lon=${lon}&date=${hour(Date.now() - 3600000)}&last_date=${hour(Date.now() + 48 * 3600000)}`);
    if (!resp.ok) throw new Error(`Bright Sky HTTP ${resp.status}`);
    const json = await resp.json();
    const sources = new Map((json.sources || []).filter(s => s.observation_type === 'forecast').map(s => [s.id, s]));
    const station = [...sources.values()].sort((a, b) => (a.distance ?? 1e9) - (b.distance ?? 1e9))[0];
    if (!station || !(station.distance <= 25000)) throw new Error('no MOSMIX station within 25 km of this airport');
    const blocks = (json.weather || []).filter(w => w.source_id === station.id).map(w => {
        const visSm = w.visibility !== null && w.visibility !== undefined ? +(w.visibility / 1609.34).toFixed(2) : null;
        return { time: w.timestamp.slice(0, 16) + ':00Z', cat: _mosCat(null, visSm, null, w.cloud_cover ?? null),
            windDir: w.wind_direction ?? null, windSpd: w.wind_speed !== null && w.wind_speed !== undefined ? w.wind_speed / 1.852 : null,
            gust: w.wind_gust_speed ? w.wind_gust_speed / 1.852 : null, precipPct: w.precipitation_probability ?? null,
            precip: w.precipitation ?? null, cigFt: null, cigLong: 'Not forecast', visSm, lowCov: null, midCov: null, highCov: null,
            totalCov: w.cloud_cover ?? null, rh: w.relative_humidity ?? null, slp: w.pressure_msl ?? null, weatherCode: null,
            wxText: w.condition && w.condition !== 'dry' ? w.condition[0].toUpperCase() + w.condition.slice(1) : null,
            tmp: w.temperature ?? null, dpt: w.dew_point ?? null };
    });
    const name = String(station.station_name || '').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
    blocks.note = `MOSMIX: DWD's forecast for the ${name} weather station (${(station.distance / 1000).toFixed(1)} km away). It has no ceiling, so the colour comes from visibility only. Source: Bright Sky.`;
    return blocks;
}
'''.split('\n')

# Detail panel: the sources' own wording, and thunder / cloud rows
replace_run(['const vis = b.visSm !== null', "? (b.visSm >= 6 ? '6+ SM' : b.visSm >= 1 ? `${b.visSm.toFixed(1)} SM` : `${b.visSm.toFixed(2)} SM`)", ": '--';"],
            ['const vis = b.visLong ?? (b.visSm !== null', "    ? (b.visSm >= 6 ? '6+ SM' : b.visSm >= 1 ? `${b.visSm.toFixed(1)} SM` : `${b.visSm.toFixed(2)} SM`)", "    : '--');"])
replace_run(["const cig = b.cigFt !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()} ft AGL` : '--';"],
            ["const cig = b.cigFt !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()} ft AGL` : (b.cigLong ?? '--');"])
replace_run(["const wx  = _wmoDesc(b.weatherCode);"], ["const wx  = b.wxText ?? _wmoDesc(b.weatherCode);"])
replace_run(["const pp = b.precipPct !== null ? `${Math.round(b.precipPct)}%` : '--';"],
            ["const pp = b.ppLong ?? (b.precipPct !== null ? `${Math.round(b.precipPct)}%` : '--');"])
i = find_run(["${row('Precip Amount', pr)}"])
pad = indent(i)
lines[i + 1:i + 1] = [pad + "${row('Thunder Probability', b.thunderPct !== null && b.thunderPct !== undefined ? `${Math.round(b.thunderPct)}%` : '--')}",
                      pad + "${row('Cloud', b.skyText || '--')}",
                      pad + "${row('Lowest Cloud Base', b.cloudBase || '--')}"]

# Timeline cards
replace_run(["const cig = b.cigFt     !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()}'` : '--';"],
            ["const cig = b.cigShort ?? (b.cigFt !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()}'` : '--');"])
replace_run(['const vis = b.visSm     !== null', "? (b.visSm >= 6 ? '6+sm' : b.visSm >= 1 ? `${b.visSm.toFixed(1)}sm` : `${b.visSm.toFixed(2)}sm`)", ": '--';"],
            ['const vis = b.visShort ?? (b.visSm !== null', "    ? (b.visSm >= 6 ? '6+sm' : b.visSm >= 1 ? `${b.visSm.toFixed(1)}sm` : `${b.visSm.toFixed(2)}sm`)", "    : '--');"])

# Compare cards
replace_run(["const cig     = b.cigFt   !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()}'` : '--';"],
            ["const cig     = b.cigShort ?? (b.cigFt !== null ? `${(Math.round(b.cigFt/100)*100).toLocaleString()}'` : '--');"])
replace_run(["const vis     = b.visSm   !== null ? (b.visSm >= 6 ? '6+sm' : b.visSm >= 1 ? `${b.visSm.toFixed(1)}sm` : `${b.visSm.toFixed(2)}sm`) : '--';"],
            ["const vis     = b.visShort ?? (b.visSm !== null ? (b.visSm >= 6 ? '6+sm' : b.visSm >= 1 ? `${b.visSm.toFixed(1)}sm` : `${b.visSm.toFixed(2)}sm`) : '--');"])
replace_run(["_MOS_MODELS.map(m => _fetchMosOpenMeteo(lat, lon, m).catch(() => []))"],
            ["_MOS_MODELS.map(m => _fetchMos(icao, lat, lon, m).catch(() => []))"])

# One source
replace_run(["const blocks = await _fetchMosOpenMeteo(lat, lon, model);", "content.innerHTML = _renderMosTimeline(blocks);"],
            ["const blocks = await _fetchMos(icao, lat, lon, model);",
             "content.innerHTML = (blocks.note ? `<p style=\"padding:8px 12px 0;font-size:10px;line-height:1.4;opacity:0.65;\">${blocks.note}</p>` : '') + _renderMosTimeline(blocks);"])

# The airport's sources
i = find_run(["if (!_mosCurrentModel || !_MOS_MODELS.includes(_mosCurrentModel)) _mosCurrentModel = _MOS_MODELS[0];"])
lines[i:i] = [indent(i) + "_MOS_MODELS = _mosIsUs(icao) ? _MOS_SOURCES_US : _MOS_SOURCES_WORLD;"]

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')
