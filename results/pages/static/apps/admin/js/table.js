(()=>{var c=class extends window.wagtailStreamField.blocks.StructBlockDefinition{render(r,e,a,n){let o=super.render(r,e,a,n),i=o.childBlocks.data,d=`
        <div>
            <label class="w-field__label">
                Paste from clipboard
            </label>
            <div class="w-field__wrapper data-field-wrapper">
                <button class="button button-small button-secondary paste-as-text">
                    Create as text
                </button>
                <button class="button button-small button-secondary paste-as-rich-text">
                    Create as rich text
                </button>
            </div>
        </div>
    `.trim(),l=document.createElement("template");l.innerHTML=d;let s=document.getElementById(e+"-options").closest('div[data-contentpath="options"]'),u=s.parentNode.insertBefore(l.content.firstChild,s.nextSibling);return u.querySelector(".paste-as-text").addEventListener("click",this.getClickHandler(i,"text")),u.querySelector(".paste-as-rich-text").addEventListener("click",this.getClickHandler(i,"rich_text")),o}getClickHandler(r,e){let a=this;return function(n){navigator.clipboard.readText().then(o=>{a.pasteFromClipboard(o,r,e)}),n.preventDefault()}}pasteFromClipboard(r,e,a){let n=(r||"").replace(/^\n+|\n+$/g,"").split(`
`).map(t=>t.split("	")),o=n[0].length;if(n.length<2||o<2||!n.every(t=>t.length==o))return;e.clear();let i=e.childBlockDefsByName[a],l={text:function(t){return t},rich_text:this.convertTextToDraftail}[a];for(let t=0;t<o;t++)e.insertColumn(t,i),e.columns[t].headingInput.value=n[0][t];for(let t=1;t<n.length;t++){e.insertRow(t-1);for(let s=0;s<o;s++)e.rows[t-1].blocks[s].setState(l(n[t][s]))}}convertTextToDraftail(r){return window.Draftail.createEditorStateFromRaw({blocks:[{type:"unstyled",depth:0,text:r,inlineStyleRanges:[],entityRanges:[]}],entityMap:{}})}};window.telepath.register("v1.atomic_elements.tables.Table",c);})();
//# sourceMappingURL=table.js.map
