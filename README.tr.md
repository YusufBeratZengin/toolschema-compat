# toolschema-compat

**Araç (function calling) JSON Schema'larını Gemini, OpenAI strict kipi ve Anthropic'in kabul ettiği alt kümelere göre denetleyen, güvenle dönüştüren ve yapılan her değişikliği kayıplı/kayıpsız (`lossy`) bilgisiyle raporlayan Python kütüphanesi ve CLI.**

[English Documentation (README.md)](./README.md) · [Değişiklik Günlüğü (CHANGELOG.md)](./CHANGELOG.md) · [Katkı Rehberi (CONTRIBUTING.md)](./CONTRIBUTING.md)

---

## Kurulum ve 30 Saniyelik Örnek

```bash
pipx install toolschema-compat
# veya sanal ortam içinde:
pip install toolschema-compat
```

Bir MCP `tools/list` JSON dosyasını (`examples/tools.json`) Google Gemini hedefine göre denetleyin ve dönüştürün:

```bash
toolschema-compat check examples/tools.json --target gemini
toolschema-compat fix examples/tools.json --target gemini
```

### Örnek Terminal Çıktısı (`examples/tools.json` Üzerinde Doğrulanmış)

Aşağıdaki CLI çıktısı [`examples/tools.json`](./examples/tools.json) dosyası üzerinde `toolschema-compat` çalıştırılarak üretilmiştir ve test paketinde (`tests/test_cli_and_report.py`) otomatik olarak doğrulanır:

```text
$ toolschema-compat check examples/tools.json --target gemini
[FAIL] target=gemini: 9 issue(s) found (2 require lossy fix)
  1. [GEMINI_REF_DEFS] $.tools[0].inputSchema.$defs: Removed `$defs` container after inlining local references. (source: https://github.com/google-gemini/gemini-cli/issues/13326)
  2. [GEMINI_REF_DEFS] $.tools[0].inputSchema.properties.filter.$ref: Inlined `$ref` ('#/$defs/IssueFilter') into `$.properties.filter`. (source: https://github.com/google-gemini/gemini-cli/issues/13326)
  3. [GEMINI_UNSUPPORTED_KEYWORD] $.tools[0].inputSchema.$schema: Removed unsupported metadata keyword `$schema`. (source: https://github.com/thClaws/thClaws/issues/172)
  4. [GEMINI_CONST] $.tools[0].inputSchema.properties.filter.properties.state.const: Converted `const` keyword to single-element `enum`. (source: https://ai.google.dev/api/caching#Schema)
  5. [GEMINI_TYPE_ARRAY] $.tools[0].inputSchema.properties.filter.properties.labels.type: Converted `type` array `['array', 'null']` to scalar type `array` with `nullable: true`. (source: https://github.com/taylorwilsdon/google_workspace_mcp/issues/1099)
  6. [GEMINI_UNSUPPORTED_CONSTRAINT] [lossy] $.tools[0].inputSchema.properties.AssigneeEmail.pattern: Removed unsupported validation constraint `pattern`. (source: https://ai.google.dev/api/caching#Schema)
  7. [GEMINI_UNSUPPORTED_FORMAT] [lossy] $.tools[0].inputSchema.properties.AssigneeEmail.format: Removed unsupported `format` value `'email'` for `gemini`. (source: https://ai.google.dev/api/caching#Schema)
  8. [GEMINI_ANYOF_NULL] $.tools[0].inputSchema.properties.cursor.anyOf: Collapsed `anyOf` with `null` into `nullable: true`. (source: https://ai.google.dev/api/caching#Schema)
  9. [GEMINI_UNSUPPORTED_KEYWORD] $.tools[0].inputSchema.properties.cursor.default: Removed unsupported metadata keyword `default`. (source: https://github.com/thClaws/thClaws/issues/172)

$ toolschema-compat fix examples/tools.json --target gemini -o fixed-gemini.json
[FIXED] target=gemini: 9 change(s) applied (2 lossy, lossy=true)
  Deleted constraints: pattern, format
  1. [GEMINI_REF_DEFS] [lossy: false] $.tools[0].inputSchema.$defs: Removed `$defs` container after inlining local references. (source: https://github.com/google-gemini/gemini-cli/issues/13326)
  2. [GEMINI_REF_DEFS] [lossy: false] $.tools[0].inputSchema.properties.filter.$ref: Inlined `$ref` ('#/$defs/IssueFilter') into `$.properties.filter`. (source: https://github.com/google-gemini/gemini-cli/issues/13326)
  ...
```

---

## Neden `toolschema-compat`?

Birden çok LLM sağlayıcısına araç (tool/function calling) veren yapay zekâ ajanları veya Model Context Protocol (MCP) sunucuları geliştirirken, Pydantic ya da FastMCP'nin ürettiği standart JSON Schema çıktıları sağlayıcı API'lerinde sıkça HTTP 400 hatasıyla reddedilir:

- **Google Gemini:** `$defs` ve `$ref` referanslarını ([gemini-cli#13326](https://github.com/google-gemini/gemini-cli/issues/13326)), `["string", "null"]` gibi `type` dizilerini ([google_workspace_mcp#1099](https://github.com/taylorwilsdon/google_workspace_mcp/issues/1099)), `additionalProperties`, `$schema`, `const` anahtarlarını ve desteklenmeyen `format` değerlerini ([thClaws#172](https://github.com/thClaws/thClaws/issues/172)) reddeder.
- **OpenAI Strict Kipi (`strict: true`):** Her nesnede `"additionalProperties": false` bulunmasını ([prism#940](https://github.com/prism-php/prism/issues/940)), `properties` içindeki tüm alanların `required` listesinde yer almasını ve opsiyonel alanların `nullable` birleşim (`["string", "null"]`) yapılmasını ([Archon#1843](https://github.com/coleam00/Archon/issues/1843)) zorunlu tutar; `pattern` ve sayısal sınır kısıtlarını reddeder.
- **Anthropic Tool Use (`input_schema`):** Kök şemanın `"type": "object"` olmasını şart koşar, OpenAPI `nullable: true` ve `oneOf` anahtarlarını kabul etmez.

`toolschema-compat`:
1. **Sağlayıcı kurallarını sürüm ve kaynak URL bağlantılı veri dosyalarında (`rules/*.toml`) tutar.**
2. **Anlamı daraltan veya doğrulama kısıtı silen değişiklikleri `lossy: true` olarak işaretler** ve silinen kısıtları (`deleted_constraints`: ör. `pattern`, `format`) açıkça listeler.
3. **Ham JSON Schema, tekil araç zarfları, Gemini `parametersJsonSchema` alanı ve MCP `tools/list` çıktılarını doğrudan okur.**
4. **Döngüsel `$ref` referanslarında sonsuz döngüye girmez ve dönüşümler idempotenttir** (iki kez uygulandığında aynı sonucu verir).

---

## Kullanım Senaryoları

### 1. MCP Sunucusunu Gemini CLI'ya Bağlamadan Önce Kontrol
```bash
toolschema-compat check examples/tools.json --target gemini
```

### 2. OpenAI Strict Kipi İçin Otomatik Düzeltme ve Raporlama
```bash
toolschema-compat fix examples/tools.json \
  --target openai-strict \
  --envelope openai \
  --output openai-tools.json \
  --report openai-report.json
```

### 3. CI Hattında Üç Sağlayıcıya Uygunluk ve Kayıpsız Dönüşüm Kapısı
```bash
toolschema-compat check examples/tools.json --target all
toolschema-compat fix examples/tools.json --target anthropic --fail-on-lossy -o anthropic-tools.json
```

---

## Çalışma Zamanı Bağımlılıkları

**Sıfır çalışma zamanı bağımlılığı.** `toolschema-compat` yalnızca Python ≥ 3.11 standart kütüphanesini (`tomllib`, `json`, `argparse`, `dataclasses`, `pathlib`, `copy`, `functools`) kullanır. Böylece Pydantic, FastAPI, MCP SDK veya LangChain sürümleriyle hiçbir paket çakışması yaratmaz.

---

## Sınırlar ve Dürüstlük Notları (`NEEDS_SOURCE`)

- **Canlı API doğrulamasının yerini tutmaz:** Bu araç sağlayıcıların resmî belgelerine ve doğrulanmış hata kayıtlarına dayalı statik şema denetimi ve dönüşümü yapar.
- **Belgelendirilmemiş sağlayıcı sınırları (`NEEDS_SOURCE`):** Sağlayıcıların sunucu tarafında uyguladığı ancak resmî belgelerde sabit bir sayı olarak yayınlamadığı sınırlar (ör. Gemini'nin model sürümlerine göre değişen maksimum iç içe geçme derinliği, OpenAI strict gramer derleme bütçesi, Anthropic birleşim dalı karmaşıklık sınırı) tahmin edilmez; kural dosyalarında açıkça `verification_status = "NEEDS_SOURCE"` olarak işaretlenir (`toolschema-compat rules --target all`).
- **`lossy: true` uyarılarını göz ardı etmeyin:** Sağlayıcı `pattern` veya `format` gibi kısıtları desteklemediği için bu alanlar şemadan silindiğinde rapor `lossy: true` üretir. Modelden gelen araç argümanlarını kendi uygulama kodunuzda her zaman doğrulayın.

---

## Lisans

MIT Lisansı — Copyright (c) 2026 Yusuf Berat Zengin. Ayrıntılar için [LICENSE](./LICENSE) dosyasına bakın.
