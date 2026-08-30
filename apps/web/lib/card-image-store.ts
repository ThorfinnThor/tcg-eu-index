export type StoredCardImage = {
  body: ArrayBuffer;
  contentType: string;
  etag: string;
};

export async function readCardImage(key: string): Promise<StoredCardImage | null> {
  void key;
  return null;
}
