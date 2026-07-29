alter table public.document_pages
  add column crop_left numeric(6, 5) null check (
    crop_left is null
    or (
      crop_left >= 0
      and crop_left <= 1
    )
  ),
  add column crop_top numeric(6, 5) null check (
    crop_top is null
    or (
      crop_top >= 0
      and crop_top <= 1
    )
  ),
  add column crop_right numeric(6, 5) null check (
    crop_right is null
    or (
      crop_right >= 0
      and crop_right <= 1
    )
  ),
  add column crop_bottom numeric(6, 5) null check (
    crop_bottom is null
    or (
      crop_bottom >= 0
      and crop_bottom <= 1
    )
  ),
  add constraint document_pages_crop_bounds_complete check (
    (
      crop_left is null
      and crop_top is null
      and crop_right is null
      and crop_bottom is null
    )
    or (
      crop_left is not null
      and crop_top is not null
      and crop_right is not null
      and crop_bottom is not null
      and crop_left < crop_right
      and crop_top < crop_bottom
    )
  );
