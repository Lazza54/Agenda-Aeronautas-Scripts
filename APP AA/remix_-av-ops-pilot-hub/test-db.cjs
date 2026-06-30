const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

function loadEnv() {
  const envPath = path.join(__dirname, '.env.local');
  const content = fs.readFileSync(envPath, 'utf8');
  const env = {};
  content.split('\n').forEach(line => {
    const match = line.match(/^\s*([\w.\-]+)\s*=\s*(.*)?\s*$/);
    if (match) {
      let key = match[1];
      let value = match[2] || '';
      if (value.length > 0 && value.charAt(0) === '"' && value.charAt(value.length - 1) === '"') {
        value = value.substring(1, value.length - 1);
      }
      env[key] = value;
    }
  });
  return env;
}

async function test() {
  const env = loadEnv();
  const url = env.VITE_SUPABASE_URL;
  const key = env.VITE_SUPABASE_ANON_KEY;

  const supabase = createClient(url, key);

  console.log('Listando arquivos do bucket relatorios na pasta 3394...');
  const { data: files, error } = await supabase
    .storage
    .from('relatorios')
    .list('3394');

  if (error) {
    console.error('Erro ao listar arquivos:', error.message);
    return;
  }

  console.log('Arquivos encontrados:', JSON.stringify(files, null, 2));

  for (const file of files) {
    console.log(`\n--- Baixando conteúdo de ${file.name} ---`);
    const { data: blob, error: dlErr } = await supabase
      .storage
      .from('relatorios')
      .download(`3394/${file.name}`);

    if (dlErr) {
      console.error('Erro no download:', dlErr.message);
    } else {
      const text = await blob.text();
      console.log('Tamanho em caracteres:', text.length);
      console.log('Primeiras 5 linhas do CSV:');
      console.log(text.split('\n').slice(0, 5).join('\n'));
    }
  }
}

test();
