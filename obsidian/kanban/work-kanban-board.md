---

kanban-plugin: board

---

## BACKLOG

- [TTS-1010](tasks/TTS-1010.md): /say voice: + configurable default voice (/voice-clone set-default) + resolve_instruct() voice-default

## TODO

## PLAN

## INPROGRESS

## REVIEW

## DONE

- [TTS-1009](tasks/TTS-1009.md): Discord slash command /voice-clone (create/list/edit/delete/test)
- [TTS-1008](tasks/TTS-1008.md): daemon fast path ล้มเหลว "no audio produced" เมื่อ out_path เป็น relative (cwd ของ launchd = /)
- [TTS-1007](tasks/TTS-1007.md): เพิ่ม mood presets ใหม่ (งอน/เขิน/ภูมิใจ/กังวล) + A/B validate ว่าโมเดลแยกเสียงจริง
- [TTS-1006](tasks/TTS-1006.md): /say — เพิ่ม language override กัน TTS ออกเสียงผิดภาษา (lang_code ผ่าน daemon protocol)
- [TTS-1005](tasks/TTS-1005.md): /transcribe — อัปโหลดไฟล์เสียง วิเคราะห์เป็นข้อความ + emoji mood พร้อมใช้กับ /say
- [TTS-1004](tasks/TTS-1004.md): เปลี่ยน ?say prefix command เป็น slash command /say
- [TTS-1003](tasks/TTS-1003.md): ?say เปลี่ยนลิมิตเป็นต่อบรรทัด + จำนวนบรรทัดไม่จำกัด
- [TTS-1002](tasks/TTS-1002.md): ?say รับข้อความหลายบรรทัด (array) + auto mood จาก emoji
- [TTS-1001](tasks/TTS-1001.md): Prefix command ?say ให้บอทพูดใน voice channel ด้วยเสียง Liino
## CLOSED

%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false,false,false,false]}
```
%%
