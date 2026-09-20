/**
 * Beacon Community Resource Widget v2.1
 *
 * <script src="https://mrstewood.github.io/beacon/embed/widget.js"
 *         data-county="laurel" data-need="food" data-theme="light" data-limit="10"></script>
 *
 * Security: All resource data is escaped before HTML insertion.
 * External links use rel="noopener noreferrer".
 */
(function(){
    const D='https://mrstewood.github.io/beacon/data/resources.json';
    const NL={addiction:"Addiction & Recovery",clothing:"Clothing & Supplies",community:"Community",crisis:"Crisis & Safety",documents:"ID & Documents",education:"Education",family:"Family & Children",food:"Food & Water",health:"Healthcare",housing:"Housing",jobs:"Jobs & Income",legal:"Legal Aid","mental-health":"Mental Health",shelter:"Shelter & Sleep",transportation:"Transportation",veterans:"Veterans"};
    const s=document.currentScript;
    const county=s?.getAttribute('data-county')||'';
    const need=s?.getAttribute('data-need')||'';
    const theme=s?.getAttribute('data-theme')||'light';
    const limit=parseInt(s?.getAttribute('data-limit')||'50');

    // HTML escaping to prevent XSS
    function esc(str){
        if(!str)return'';
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    // Safe URL - only allow http/https
    function safeUrl(url){
        if(!url)return'#';
        const u=esc(url);
        if(u.startsWith('http://')||u.startsWith('https://'))return u;
        return'#';
    }

    const box=document.createElement('div');
    box.className='beacon-widget';
    const st=document.createElement('style');
    st.textContent=`
        .beacon-widget{font-family:-apple-system,system-ui,sans-serif;max-width:600px;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}
        .beacon-widget.tl{background:#fff;color:#0f172a}.beacon-widget.td{background:#0f172a;color:#f1f5f9}
        .bw-hdr{padding:.85rem 1rem;font-weight:600;font-size:1rem}.beacon-widget.tl .bw-hdr{background:#1d4ed8;color:#fff}.beacon-widget.td .bw-hdr{background:#3b82f6;color:#fff}
        .bw-list{max-height:400px;overflow-y:auto}
        .bw-i{padding:.65rem 1rem;border-bottom:1px solid #e2e8f0}.beacon-widget.td .bw-i{border-color:#334155}.bw-i:last-child{border-bottom:none}
        .bw-n{font-weight:500;margin-bottom:.15rem}.bw-n a{color:#1d4ed8;text-decoration:none}.bw-n a:hover{text-decoration:underline}
        .beacon-widget.td .bw-n a{color:#60a5fa}
        .bw-m{font-size:.82rem;color:#64748b}.beacon-widget.td .bw-m{color:#94a3b8}
        .bw-t{display:inline-block;background:#dbeafe;color:#1e40af;padding:.1rem .45rem;border-radius:9999px;font-size:.7rem;font-weight:500;margin-top:.25rem}
        .bw-ft{padding:.6rem 1rem;font-size:.75rem;text-align:center;border-top:1px solid #e2e8f0}
        .beacon-widget.tl .bw-ft{background:#f8fafc;color:#64748b}.beacon-widget.td .bw-ft{background:#020617;color:#94a3b8;border-color:#334155}
        .bw-ft a{color:#1d4ed8;text-decoration:none}
    `;
    document.head.appendChild(st);
    box.innerHTML='<div style="padding:1.5rem;text-align:center;color:#64748b">Loading…</div>';
    s.parentNode.insertBefore(box,s.nextSibling);

    fetch(D).then(function(r){return r.json()}).then(function(d){
        var res=d.resources;
        if(county)res=res.filter(function(r){return r.county.toLowerCase()===county.toLowerCase()});
        if(need)res=res.filter(function(r){return r.needs.indexOf(need)!==-1});
        res=res.slice(0,limit);
        var hdr=[county?county+' County':'',need?(NL[need]||need):'','Resources'].filter(Boolean).join(' ');
        var h='<div class="beacon-widget '+(theme==='dark'?'td':'tl')+'"><div class="bw-hdr">'+esc(hdr)+'</div><div class="bw-list">';
        if(!res.length)h+='<div class="bw-i">No resources found.</div>';
        else res.forEach(function(r){
            var ph=r.phones&&r.phones.length?'&#x1F4DE; <a href="tel:'+esc(r.phones[0])+'">'+esc(r.phones[0])+'</a>':'';
            var lk=r.url?' &middot; <a href="'+safeUrl(r.url)+'" target="_blank" rel="noopener noreferrer">Website</a>':'';
            var tags=r.needs.slice(0,3).map(function(n){return'<span class="bw-t">'+esc(NL[n]||n)+'</span>'}).join('');
            h+='<div class="bw-i"><div class="bw-n"><a href="'+safeUrl(r.url||'#')+'" target="_blank" rel="noopener noreferrer">'+esc(r.name)+'</a></div><div class="bw-m">'+ph+lk+(r.address&&r.address!=='Statewide'?'<br>&#x1F4CD; '+esc(r.address):'')+'</div>'+(tags?'<div style="margin-top:.2rem">'+tags+'</div>':'')+'</div>';
        });
        h+='</div><div class="bw-ft">Powered by <a href="https://mrstewood.github.io/beacon/" target="_blank" rel="noopener noreferrer">Beacon</a></div></div>';
        box.outerHTML=h;
    })['catch'](function(){
        box.innerHTML='<div class="beacon-widget"><div style="padding:1.5rem;text-align:center">Unable to load resources.</div></div>';
    });
})();
