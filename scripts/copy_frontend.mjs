import {copyFileSync, mkdirSync} from 'node:fs';
mkdirSync('static/js', {recursive:true});
copyFileSync('node_modules/@alpinejs/csp/dist/cdn.min.js', 'static/js/alpine.min.js');
