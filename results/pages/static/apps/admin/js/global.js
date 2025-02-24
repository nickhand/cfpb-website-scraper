(()=>{global=globalThis;var n=location.hostname.split(".")[0],a=document.querySelector("body");a.setAttribute("data-env",n);window.addEventListener("DOMContentLoaded",function(){let t=function(e){e.detail.data.title=e.detail.filename};document.addEventListener("wagtail:documents-upload",t),document.addEventListener("wagtail:images-upload",t)});})();
//# sourceMappingURL=global.js.map
