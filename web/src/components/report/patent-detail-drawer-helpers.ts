export function getPatentLinks(patentId: string) {
  return {
    googlePatents: `https://patents.google.com/patent/${patentId}`,
    espacenet: `https://worldwide.espacenet.com/patent/search?q=pn%3D${patentId}`,
  };
}
