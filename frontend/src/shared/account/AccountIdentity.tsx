import { useEffect, useState } from 'react';
import { apiFile } from '../api/client';

const AVATAR_EMOJIS = ['🏋️', '💪', '🏃', '🚴', '🥗', '⚡', '🎯', '🔥'] as const;

function avatarSource(value: string | null | undefined, allowBlob = false): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const source = url.href;
    if (source.startsWith('https://') || source.startsWith('http://')) return source;
    if (allowBlob && source.startsWith('blob:') && url.origin === window.location.origin) {
      return source;
    }
  } catch {
    return null;
  }
  return null;
}

function avatarFallback(name: string): string {
  const hash = Array.from(name.trim()).reduce(
    (value, character) => (value * 31 + (character.codePointAt(0) ?? 0)) >>> 0,
    0,
  );
  return AVATAR_EMOJIS[hash % AVATAR_EMOJIS.length] ?? AVATAR_EMOJIS[0];
}

export function accountRoleLabel(isRoot: boolean, isCoach: boolean): string {
  if (isRoot) return isCoach ? 'Root · Тренер' : 'Root · Личный режим';
  if (isCoach) return 'Тренер';
  return 'Клиент';
}

export function AccountAvatar({
  className = 'account-identity__avatar',
  customAvatarVersion,
  name,
  photoUrl,
  previewUrl,
}: {
  className?: string;
  customAvatarVersion?: string | null;
  name: string;
  photoUrl?: string | null;
  previewUrl?: string | null;
}) {
  const [failedPhotoUrls, setFailedPhotoUrls] = useState<ReadonlySet<string>>(() => new Set());
  const [privateAvatar, setPrivateAvatar] = useState<{
    version: string;
    url: string | null;
  } | null>(null);

  useEffect(() => {
    if (!customAvatarVersion) return;
    let active = true;
    let objectUrl: string | null = null;
    void apiFile('/api/v1/me/avatar')
      .then(({ blob }) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPrivateAvatar({ version: customAvatarVersion, url: objectUrl });
      })
      .catch(() => {
        if (active) setPrivateAvatar({ version: customAvatarVersion, url: null });
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [customAvatarVersion]);

  const customUrl =
    privateAvatar && privateAvatar.version === customAvatarVersion ? privateAvatar.url : null;
  const privateUrl = avatarSource(previewUrl, true) || avatarSource(customUrl, true);
  const providerUrl = avatarSource(photoUrl);
  const selectedUrl =
    privateUrl && !failedPhotoUrls.has(privateUrl)
      ? privateUrl
      : providerUrl && !failedPhotoUrls.has(providerUrl)
        ? providerUrl
        : null;

  return (
    <span className={className} aria-hidden="true">
      {selectedUrl ? (
        <img
          src={selectedUrl}
          alt=""
          referrerPolicy="no-referrer"
          onError={() =>
            setFailedPhotoUrls((current) => {
              const next = new Set(current);
              next.add(selectedUrl);
              return next;
            })
          }
        />
      ) : (
        avatarFallback(name)
      )}
    </span>
  );
}

export function AccountIdentity({
  avatarClassName,
  className = 'account-identity',
  customAvatarVersion,
  name,
  photoUrl,
  role,
}: {
  avatarClassName?: string;
  className?: string;
  customAvatarVersion?: string | null;
  name: string;
  photoUrl?: string | null;
  role: string;
}) {
  return (
    <span className={className}>
      <AccountAvatar
        className={avatarClassName}
        customAvatarVersion={customAvatarVersion}
        name={name}
        photoUrl={photoUrl}
      />
      <span className="account-identity__copy">
        <strong className="account-identity__name">{name}</strong>
        <small className="account-identity__role">{role}</small>
      </span>
    </span>
  );
}
