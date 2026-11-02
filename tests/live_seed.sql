-- Known data for tests/test_live.py. Load it into a throwaway database only, after the backend has migrated it.
insert into invite_codes (code) values ('sdk-live');

insert into memes (slug, title, aliases, summary, body, usage_examples, categories, heat) values
    ('tang-ping', '躺平', '{摆烂,lie flat}', '不想努力了', '躺平的正文', '{我躺平了}', '{网络}', 90),
    ('yyds', 'YYDS', '{永远的神,yong yuan de shen}', '夸人的话', 'YYDS的正文', '{你真是YYDS}', '{网络}', 80),
    ('ban-wei', '班味', '{上班味}', '上班上出来的气质', '班味的正文', '{}', '{职场}', 70),
    ('da-gong-ren', '打工人', '{打工仔,社畜}', '上班的人', '打工人的正文', '{}', '{职场}', 60),
    ('50-percent', '百分之50%', '{}', '带符号的标题', '正文', '{}', '{}', 50),
    ('under_score', 'Snake_Case 梗', '{}', '带下划线的标题', '正文', '{}', '{}', 40);

insert into meme_relations (meme_id, related_id)
select a.id, b.id from memes a, memes b where a.slug = 'tang-ping' and b.slug = 'da-gong-ren';

insert into sticker_packs (id, title, description, tags, status) values
    ('33333333-3333-3333-3333-333333333333', '猫猫', '猫', '{可爱,动物}', 'published');

-- A valid 1x1 PNG.
insert into stickers (id, pack_id, position, caption, mime, data) values
    ('44444444-4444-4444-4444-444444444444', '33333333-3333-3333-3333-333333333333', 0, '震惊', 'image/png',
     decode('89504e470d0a1a0a0000000d4948445200000001000000010806000000' || '1f15c4890000000d49444154789c6360000002000001' || '0001e221bc330000000049454e44ae426082', 'hex')),
    ('55555555-5555-5555-5555-555555555555', '33333333-3333-3333-3333-333333333333', 1, '开心', 'image/png',
     decode('89504e470d0a1a0a0000000d4948445200000001000000010806000000' || '1f15c4890000000d49444154789c6360000002000001' || '0001e221bc330000000049454e44ae426082', 'hex'));

insert into personas (id, title, description, prompt, tags, status, meme_ids, pack_ids) values
    ('11111111-1111-1111-1111-111111111111', '毒舌老哥', '说话很冲', '你是毒舌老哥', '{搞笑}', 'published',
     (select array_agg(id) from memes where slug in ('tang-ping', 'da-gong-ren')), '{33333333-3333-3333-3333-333333333333}'),
    ('22222222-2222-2222-2222-222222222222', '温柔姐姐', '说话很软', '你是温柔姐姐', '{治愈}', 'published',
     (select array_agg(id) from memes where slug = 'yyds'), '{}');
