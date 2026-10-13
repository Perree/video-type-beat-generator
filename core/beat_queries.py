"""Fixed public read queries; catalog metadata and separate preview resolution."""
PROFILE_QUERY = """query($username:String!){
  profileByUsername(username:$username){memberId username}
}"""
TRACKS_QUERY = """query($memberId:String!,$page:Int,$size:Int){
  profileTracks(memberId:$memberId,page:$page,size:$size){
    totalElements totalPages number last
    content{id title v2Id seoMetadata{slug} metadata{tags}
      bundle{hls{duration} stream{duration}} profile{memberId}}
  }
}"""

# Short links (bsta.rs) for the description: read-only, separate from catalog sync.
SHARE_QUERY = """query($memberId:String!,$page:Int,$size:Int){
  profileTracks(memberId:$memberId,page:$page,size:$size){
    totalElements totalPages number last
    content{id shareUrl profile{memberId}}
  }
}"""

# Public preview resolution is separate from catalog sync; URLs are never stored.
PREVIEWS_QUERY = """query($memberId:String!,$page:Int,$size:Int){
  profileTracks(memberId:$memberId,page:$page,size:$size){
    totalElements totalPages number last
    content{id bundle{hls{url duration}} profile{memberId}}
  }
}"""
