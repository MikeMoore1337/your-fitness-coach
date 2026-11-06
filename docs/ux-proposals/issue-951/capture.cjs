const { pathToFileURL } = require('url');
const { createRequire } = require('module');
const fs = require('fs');
const path = require('path');
const playwrightRoot = process.env.YFC_PLAYWRIGHT_ROOT || path.resolve(__dirname, '../../../frontend');
const { chromium, webkit } = createRequire(path.join(playwrightRoot, 'package.json'))('playwright');
const root = __dirname;
const out = path.join(root, 'evidence');
fs.mkdirSync(out, { recursive: true });
const url = pathToFileURL(path.join(root, 'preview.html')).href;
const problems = [];
async function checkGeometry(page, info) {
  const result = await page.evaluate(() => {
    const containers = [...document.querySelectorAll('.scroll')].filter((node) => node.clientWidth && node.scrollWidth > node.clientWidth + 1).map((node) => node.id);
    const small = [...document.querySelectorAll('.panel button, .panel input, .panel select')].filter((node) => {
      const box = node.getBoundingClientRect();
      return box.width && box.height && (box.width < 44 || box.height < 44);
    }).map((node) => ({tag:node.tagName,id:node.id,text:node.textContent.trim().slice(0,30),width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height}));
    return {viewport:innerWidth,doc:document.documentElement.scrollWidth,panel:document.querySelector('.panel').scrollWidth,panelWidth:document.querySelector('.panel').clientWidth,containers,small};
  });
  if (result.doc > result.viewport || result.panel > result.panelWidth + 1 || result.containers.length || result.small.length) problems.push({...info, ...result});
}
(async () => {
  for (const [engine, api] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await api.launch({headless:true});
    for (const variant of ['a', 'b']) for (const theme of ['light', 'dark']) {
      for (const width of [320,360,390,430,1280]) {
        const height = ({320:720,360:800,390:844,430:932,1280:900})[width];
        const page = await browser.newPage({viewport:{width,height},colorScheme:theme,reducedMotion:'reduce'});
        await page.goto(`${url}?variant=${variant}&theme=${theme}&state=selected`);
        await checkGeometry(page, {engine,variant,theme,width});
        await page.screenshot({path:path.join(out,`${variant}-${engine}-${width}x${height}-${theme}-selected.png`)});
        await page.close();
      }
      for (const state of ['empty','loading','error','editing','units','unknown','invalid','network','single','keyboard']) {
        const height=state==='keyboard'?430:844;
        const page=await browser.newPage({viewport:{width:390,height},colorScheme:theme,reducedMotion:'reduce'});
        await page.goto(`${url}?variant=${variant}&theme=${theme}&state=${state}`);
        if (state==='keyboard') await page.locator('#search').focus();
        await checkGeometry(page, {engine,variant,theme,state});
        await page.screenshot({path:path.join(out,`${variant}-${engine}-390x${height}-${theme}-${state}.png`)});
        await page.close();
      }
      const page = await browser.newPage({viewport:{width:390,height:844},colorScheme:theme,reducedMotion:'reduce'});
      await page.goto(`${url}?variant=${variant}&theme=${theme}&state=begin&dataset=baseline`);
      let actions=0;
      await page.getByRole('button',{name:'Добавить',exact:true}).first().click(); actions++;
      for(const q of ['Рис белый отварной','Рис бурый отварной','Гречка отварная','Куриная грудка запечённая','Творог натуральный','Яблоко свежее']) {
        await page.locator('#search').fill(q); actions++;
        await page.getByRole('button',{name:`Выбрать ${q}, Проверено YFC`,exact:true}).click(); actions++;
      }
      if ((await page.locator('#total-count').textContent()).trim() !== 'Выбрано: 6') throw Error('six selections missing');
      await page.locator('#confirm').click(); actions++;
      if(actions!==14 || await page.locator('#toast').isHidden()) throw Error('action count or result wrong');
      await page.close();
      console.log(`${engine} ${variant} ${theme}: ${actions} prototype actions`);
      if(theme==='light') {
        for (const count of [1,3]) {
          const p=await browser.newPage({viewport:{width:390,height:844}});
          await p.goto(`${url}?variant=${variant}&theme=light&state=begin&dataset=baseline`);
          let n=0;
          await p.getByRole('button',{name:'Добавить',exact:true}).first().click(); n++;
          for(const query of ['Рис белый отварной','Рис бурый отварной','Гречка отварная'].slice(0,count)) {await p.locator('#search').fill(query);n++;await p.getByRole('button',{name:`Выбрать ${query}, Проверено YFC`,exact:true}).click();n++;}
          if(!(await p.locator('#total-count').textContent()).includes(`Выбрано: ${count}`)) throw Error('incorrect count');
          await p.locator('#confirm').click();n++;
          if(n!==2*count+2) throw Error('incorrect count of actions');
          await p.close();
          console.log(`${engine} ${variant}: ${count} product(s), ${n} prototype actions`);
        }
        const p=await browser.newPage({viewport:{width:390,height:844}});
        await p.goto(`${url}?variant=${variant}&theme=light&state=begin`);
        await p.getByRole('button',{name:'Добавить',exact:true}).first().click();
        await p.locator('#search').fill('йогурт');
        await p.getByRole('button',{name:'Выбрать Йогурт натуральный, Марка А, Проверено YFC',exact:true}).click();
        await p.getByRole('button',{name:'Выбрать Йогурт натуральный, Марка Б, Open Food Facts',exact:true}).click();
        if(!(await p.locator('#total-count').textContent()).includes('Выбрано: 2')) throw Error('same-name brands merged in prototype');
        await p.goto(`${url}?variant=${variant}&theme=light&state=editing`);
        await p.getByRole('spinbutton',{name:'Количество: Йогурт натуральный, Марка А, Проверено YFC'}).fill('150');
        if(!(await p.locator('#total-values').textContent()).includes('495 ккал')) throw Error('quantity did not update total');
        await p.getByRole('button',{name:'Убрать Овсяные хлопья цельнозерновые длительной варки, Северные поля, Сообщество из подборки'}).click();
        if(await p.locator('#search').inputValue()!=='йогурт'||!(await p.locator('#total-count').textContent()).includes('Выбрано: 2')) throw Error('remove cleared search or selection');
        await p.close();
        const invalid=await browser.newPage({viewport:{width:390,height:844}});
        await invalid.goto(`${url}?variant=${variant}&theme=light&state=invalid`);
        if(!(await invalid.locator('#confirm').isDisabled())) throw Error('invalid quantity enabled confirmation');
        await invalid.goto(`${url}?variant=${variant}&theme=light&state=unknown`);
        if(!(await invalid.locator('#total-values').textContent()).includes('Б — · Ж —')) throw Error('unknown macros became numeric');
        if(!(await invalid.locator('#total-values').textContent()).includes('Клетчатка —')) throw Error('unknown fiber became numeric');
        await invalid.close();
        const units=await browser.newPage({viewport:{width:390,height:844}});
        await units.goto(`${url}?variant=${variant}&theme=light&state=units`);
        await units.locator('#amount-milk').fill('200');
        await units.locator('[data-unit=bread]').selectOption('г');
        await units.locator('#amount-bread').fill('40');
        if(!(await units.locator('#total-values').textContent()).includes('261 ккал')) throw Error('ml/serving/grams total wrong');
        await units.locator('#close').click();
        await units.getByRole('button',{name:'Добавить',exact:true}).first().click();
        if(await units.locator('#search').inputValue()!==''||!(await units.locator('#total-count').textContent()).includes('Нет выбранных продуктов')) throw Error('cancel and reopen did not reset demo');
        if(variant==='b') {
          await units.locator('#tab-search').focus();
          await units.keyboard.press('ArrowRight');
          if(await units.locator('#tab-picked').getAttribute('aria-selected')!=='true') throw Error('tab keyboard navigation failed');
        }
        await units.close();
        console.log(`${engine} ${variant}: edit/remove/search, units, cancel/reopen, invalid and unknown values passed`);
      }
    }
    await browser.close();
  }
  if(problems.length) { console.error(JSON.stringify(problems)); process.exitCode=1; }
  else console.log('No horizontal overflow or visible control under 44×44 CSS px detected in screenshot matrix.');
})().catch(error=>{console.error(error); process.exitCode=1;});
